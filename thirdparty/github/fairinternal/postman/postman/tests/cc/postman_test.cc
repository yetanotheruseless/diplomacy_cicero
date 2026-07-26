/*
Copyright (c) Meta Platforms, Inc. and affiliates.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
*/

#include <ATen/ATen.h>

#include <atomic>
#include <chrono>
#include <complex>
#include <cstdint>
#include <exception>
#include <future>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "postman/asyncclient.h"
#include "postman/blocking_counter.h"
#include "postman/client.h"
#include "postman/computationqueue.h"
#include "postman/exceptions.h"
#include "postman/queue.h"
#include "postman/serialization.h"
#include "postman/server.h"
#include "rpc.pb.h"

namespace {

using namespace std::chrono_literals;

void check(bool condition, const std::string& message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

template <typename Exception, typename Function>
void check_throws(Function&& function, const std::string& message) {
  try {
    function();
  } catch (const Exception&) {
    return;
  }
  throw std::runtime_error(message);
}

void check_tensor(
    const at::Tensor& actual,
    const at::Tensor& expected,
    const std::string& message) {
  check(
      actual.scalar_type() == expected.scalar_type() &&
          actual.sizes() == expected.sizes() &&
          at::equal(actual, expected),
      message);
}

std::string server_address(const postman::Server& server) {
  return "127.0.0.1:" + std::to_string(server.port());
}

void test_queue_and_counter() {
  check_throws<std::invalid_argument>(
      []() { postman::Queue<int> invalid(0); },
      "zero-capacity queue was accepted");

  postman::Queue<int> queue(1);
  queue.enqueue(1);
  check(
      !queue.try_enqueue(99),
      "try_enqueue accepted an item above capacity");
  std::promise<void> producer_finished;
  std::future<void> producer_status =
      producer_finished.get_future();
  std::thread producer([&]() {
    queue.enqueue(2);
    producer_finished.set_value();
  });

  check(
      producer_status.wait_for(25ms) ==
          std::future_status::timeout,
      "producer did not block on a full queue");
  check(queue.dequeue() == 1, "queue returned the wrong first item");
  check(
      producer_status.wait_for(2s) ==
          std::future_status::ready,
      "dequeue did not wake a blocked producer");
  producer.join();
  check(queue.dequeue() == 2, "queue returned the wrong second item");
  check(queue.try_enqueue(3), "try_enqueue rejected available capacity");
  check(queue.dequeue() == 3, "try_enqueue stored the wrong item");
  queue.close();
  queue.close();
  check_throws<postman::QueueClosed>(
      [&]() { queue.enqueue(3); },
      "closed queue accepted an item");
  check_throws<postman::QueueClosed>(
      [&]() { (void)queue.try_enqueue(3); },
      "closed queue accepted a non-blocking enqueue");
  check_throws<postman::QueueClosed>(
      [&]() { (void)queue.dequeue(); },
      "closed queue allowed a dequeue");

  check_throws<std::invalid_argument>(
      []() { BlockingCounter invalid(-1); },
      "negative BlockingCounter was accepted");
  BlockingCounter counter(2);
  std::atomic_int zero_results = 0;
  std::thread first([&]() {
    if (counter.DecrementCount()) {
      ++zero_results;
    }
  });
  std::thread second([&]() {
    if (counter.DecrementCount()) {
      ++zero_results;
    }
  });
  counter.Wait();
  first.join();
  second.join();
  check(
      zero_results.load() == 1,
      "BlockingCounter did not report exactly one zero transition");
  check_throws<std::logic_error>(
      [&]() { counter.Wait(); },
      "BlockingCounter allowed multiple Wait calls");
  check_throws<std::runtime_error>(
      [&]() { counter.DecrementCount(); },
      "BlockingCounter allowed underflow");
}

void test_serialization() {
  using Map = std::map<std::string, TensorNest>;
  using Vector = std::vector<TensorNest>;

  const at::Tensor transposed =
      at::arange(12, at::kFloat).reshape({3, 4}).transpose(0, 1);
  const at::Tensor conjugated = at::complex(
                                      at::tensor({1.0F, 2.0F}),
                                      at::tensor({3.0F, 4.0F}))
                                      .conj();
  TensorNest value(Map{
      {"empty_map", TensorNest(Map{})},
      {"empty_vector", TensorNest(Vector{})},
      {"nested",
       TensorNest(Vector{
           TensorNest(transposed),
           TensorNest(conjugated),
           TensorNest(at::empty({0, 3}, at::kLong)),
       })},
  });

  postman::ArrayNest proto;
  postman::detail::fill_proto_from_tensornest(&proto, value);
  check(proto.IsInitialized(), "serialized nest is not initialized");

  std::string wire;
  check(proto.SerializeToString(&wire), "nest serialization failed");
  postman::ArrayNest parsed;
  check(parsed.ParseFromString(wire), "nest parsing failed");
  TensorNest decoded =
      postman::detail::nest_proto_to_tensornest(parsed);

  const auto& decoded_map =
      std::get<Map>(decoded.value);
  check(
      decoded_map.at("empty_map").is_map(),
      "empty map did not retain its wire kind");
  check(
      decoded_map.at("empty_vector").is_vector(),
      "empty vector did not retain its wire kind");
  const auto& decoded_nested =
      std::get<Vector>(decoded_map.at("nested").value);
  check_tensor(
      decoded_nested[0].front(),
      transposed,
      "non-contiguous tensor did not round-trip logically");
  check_tensor(
      decoded_nested[1].front(),
      conjugated.resolve_conj(),
      "conjugate tensor did not round-trip logically");
  check_tensor(
      decoded_nested[2].front(),
      at::empty({0, 3}, at::kLong),
      "zero-size tensor did not round-trip");

  for (const at::ScalarType scalar_type :
       {at::kByte, at::kChar, at::kShort, at::kInt, at::kLong,
        at::kHalf, at::kFloat, at::kDouble, at::kComplexFloat,
        at::kComplexDouble, at::kBool, at::kBFloat16}) {
    const at::Tensor tensor =
        at::zeros({2, 3}, at::TensorOptions().dtype(scalar_type));
    postman::ArrayNest dtype_proto;
    postman::detail::fill_proto_from_tensornest(
        &dtype_proto, TensorNest(tensor));
    check_tensor(
        postman::detail::nest_proto_to_tensornest(
            dtype_proto)
            .front(),
        tensor,
        "tensor dtype did not round-trip");
  }

  postman::ArrayNest missing_kind;
  check_throws<std::runtime_error>(
      [&]() {
        (void)postman::detail::nest_proto_to_tensornest(
            missing_kind);
      },
      "nest without kind was accepted");

  postman::ArrayNest missing_dtype;
  missing_dtype.set_kind(postman::ArrayNest::ARRAY);
  missing_dtype.mutable_array()->set_data("");
  check_throws<std::runtime_error>(
      [&]() {
        (void)postman::detail::nest_proto_to_tensornest(
            missing_dtype);
      },
      "tensor without dtype was accepted");

  postman::ArrayNest negative_shape;
  negative_shape.set_kind(postman::ArrayNest::ARRAY);
  negative_shape.mutable_array()->set_scalar_type(
      static_cast<int>(at::kFloat));
  negative_shape.mutable_array()->add_shape(-1);
  negative_shape.mutable_array()->set_data("");
  check_throws<std::runtime_error>(
      [&]() {
        (void)postman::detail::nest_proto_to_tensornest(
            negative_shape);
      },
      "negative tensor shape was accepted");

  postman::ArrayNest wrong_size;
  wrong_size.set_kind(postman::ArrayNest::ARRAY);
  wrong_size.mutable_array()->set_scalar_type(
      static_cast<int>(at::kFloat));
  wrong_size.mutable_array()->add_shape(2);
  wrong_size.mutable_array()->set_data("bad");
  check_throws<std::runtime_error>(
      [&]() {
        (void)postman::detail::nest_proto_to_tensornest(
            wrong_size);
      },
      "malformed tensor byte count was accepted");
}

void test_computation_queue() {
  check_throws<std::invalid_argument>(
      []() { postman::ComputationQueue invalid(0); },
      "zero batch size was accepted");
  check_throws<std::invalid_argument>(
      []() {
        postman::ComputationQueue invalid(
            static_cast<std::uint32_t>(
                std::numeric_limits<int>::max()) +
            1U);
      },
      "batch size above BlockingCounter capacity was accepted");
  check_throws<std::invalid_argument>(
      []() { postman::ComputationQueue invalid(1, 0); },
      "zero pending-batch capacity was accepted");

  postman::ComputationQueue cpu_queue(2);
  check_throws<std::invalid_argument>(
      [&]() {
        std::int64_t index;
        (void)cpu_queue.compute(
            TensorNest(at::empty(
                {1},
                at::TensorOptions()
                    .dtype(at::kFloat)
                    .device(at::kMeta))),
            &index);
      },
      "non-CPU input was accepted as the first batch member");
  std::int64_t cpu_first_index = -1;
  const auto cpu_first_future = cpu_queue.compute(
      TensorNest(at::tensor({1.0F})), &cpu_first_index);
  check_throws<std::invalid_argument>(
      [&]() {
        std::int64_t index;
        (void)cpu_queue.compute(
            TensorNest(at::empty(
                {1},
                at::TensorOptions()
                    .dtype(at::kFloat)
                    .device(at::kMeta))),
            &index);
      },
      "non-CPU input was accepted within a partial batch");
  std::int64_t cpu_second_index = -1;
  const auto cpu_second_future = cpu_queue.compute(
      TensorNest(at::tensor({2.0F})), &cpu_second_index);
  auto cpu_computation = cpu_queue.get(true);
  cpu_computation->set_outputs(cpu_computation->get_inputs());
  (void)cpu_first_future.get();
  (void)cpu_second_future.get();
  check(
      cpu_first_index == 0 && cpu_second_index == 1,
      "rejected non-CPU input corrupted batch admission");
  cpu_queue.close();

  postman::ComputationQueue bounded_queue(2, 1);
  std::int64_t bounded_first_index = -1;
  const auto bounded_first_future = bounded_queue.compute(
      TensorNest(at::tensor({1.0F})), &bounded_first_index);
  std::int64_t bounded_second_index = -1;
  const auto bounded_second_future = bounded_queue.compute(
      TensorNest(at::tensor({2.0F})), &bounded_second_index);
  check_throws<std::runtime_error>(
      [&]() {
        std::int64_t index;
        (void)bounded_queue.compute(
            TensorNest(at::tensor({3.0F})), &index);
      },
      "full computation backlog did not reject a new batch");
  auto bounded_computation = bounded_queue.get(true);
  bounded_computation->set_outputs(
      bounded_computation->get_inputs());
  (void)bounded_first_future.get();
  (void)bounded_second_future.get();

  std::int64_t admitted_after_dequeue_index = -1;
  const auto admitted_after_dequeue = bounded_queue.compute(
      TensorNest(at::tensor({4.0F})),
      &admitted_after_dequeue_index);
  auto admitted_computation = bounded_queue.get(false);
  admitted_computation->set_outputs(
      admitted_computation->get_inputs());
  (void)admitted_after_dequeue.get();
  check(
      bounded_first_index == 0 && bounded_second_index == 1 &&
          admitted_after_dequeue_index == 0,
      "bounded computation backlog corrupted batch indices");
  bounded_queue.close();

  postman::ComputationQueue resized_queue(2);
  std::int64_t resized_first_index = -1;
  const auto resized_first_future = resized_queue.compute(
      TensorNest(at::tensor({1.0F})), &resized_first_index);
  resized_queue.set_batch_size(1);
  std::int64_t resized_second_index = -1;
  const auto resized_second_future = resized_queue.compute(
      TensorNest(at::tensor({2.0F})), &resized_second_index);
  auto old_size_computation = resized_queue.get(true);
  old_size_computation->set_outputs(
      old_size_computation->get_inputs());
  (void)resized_first_future.get();
  (void)resized_second_future.get();
  std::int64_t next_batch_index = -1;
  const auto next_batch_future = resized_queue.compute(
      TensorNest(at::tensor({3.0F})), &next_batch_index);
  auto new_size_computation = resized_queue.get(true);
  new_size_computation->set_outputs(
      new_size_computation->get_inputs());
  (void)next_batch_future.get();
  check(
      resized_first_index == 0 && resized_second_index == 1 &&
          next_batch_index == 0,
      "batch-size update did not preserve the active batch snapshot");
  resized_queue.close();

  postman::ComputationQueue queue(2);
  std::int64_t first_index;
  const auto first_future = queue.compute(
      TensorNest(at::tensor({1.0F, 2.0F})), &first_index);
  check_throws<std::invalid_argument>(
      [&]() {
        std::int64_t index;
        (void)queue.compute(
            TensorNest(at::tensor({1.0F, 2.0F, 3.0F})),
            &index);
      },
      "shape change within a batch was accepted");

  std::int64_t second_index;
  const auto second_future = queue.compute(
      TensorNest(at::tensor({3.0F, 4.0F})), &second_index);
  std::shared_ptr<postman::ComputationQueue::Computation>
      computation = queue.get(true);
  check_tensor(
      computation->get_inputs().front(),
      at::tensor({1.0F, 2.0F, 3.0F, 4.0F}).reshape({2, 2}),
      "batched queue inputs were not copied correctly");
  computation->set_outputs(
      TensorNest(at::tensor({10.0F, 20.0F}).reshape({2, 1})));
  check_tensor(
      first_future.get().front(),
      at::tensor({10.0F, 20.0F}).reshape({2, 1}),
      "first queued future returned the wrong output");
  check_tensor(
      second_future.get().front(),
      at::tensor({10.0F, 20.0F}).reshape({2, 1}),
      "second queued future returned the wrong output");
  check(first_index == 0 && second_index == 1, "batch indices are wrong");
  queue.close();
  queue.close();

  postman::ComputationQueue partial_queue(4);
  const at::Tensor large_input =
      at::arange(2 * 1024 * 1024, at::kFloat);
  std::shared_future<TensorNest> partial_future;
  std::int64_t partial_index = -1;
  std::thread writer([&]() {
    partial_future = partial_queue.compute(
        TensorNest(large_input), &partial_index);
  });
  auto partial = partial_queue.get(false);
  writer.join();
  check_tensor(
      partial->get_inputs().front()[0],
      large_input,
      "partial batch was resized before its writer completed");
  partial->set_outputs(
      TensorNest(at::zeros({1, 1}, at::kFloat)));
  (void)partial_future.get();
  partial_queue.close();

  postman::ComputationQueue closed_queue(1);
  std::int64_t closed_index;
  const auto closed_future = closed_queue.compute(
      TensorNest(at::zeros({1})), &closed_index);
  closed_queue.close();
  check_throws<postman::QueueClosed>(
      [&]() { (void)closed_future.get(); },
      "closing a queued computation did not resolve its future");
  check_throws<postman::QueueClosed>(
      [&]() {
        std::int64_t index;
        (void)closed_queue.compute(
            TensorNest(at::zeros({1})), &index);
      },
      "closed computation queue accepted work");

  postman::ComputationQueue partial_close_queue(2);
  std::int64_t partial_close_index;
  const auto partial_close_future = partial_close_queue.compute(
      TensorNest(at::zeros({1})), &partial_close_index);
  auto blocked_get = std::async(std::launch::async, [&]() {
    return partial_close_queue.get(true);
  });
  partial_close_queue.close();
  check(
      blocked_get.wait_for(2s) == std::future_status::ready,
      "closing a partial batch did not unblock get(wait_till_full=true)");
  check_throws<postman::QueueClosed>(
      [&]() { (void)blocked_get.get(); },
      "closing a partial batch returned an aborted computation");
  check_throws<postman::QueueClosed>(
      [&]() { (void)partial_close_future.get(); },
      "closing a partial batch did not reject its writer");
}

void test_sync_rpc() {
  postman::Server server("127.0.0.1:0");
  server.bind("add_seven", [](const TensorNest& inputs) {
    return inputs.map(
        [](const at::Tensor& tensor) { return tensor + 7; });
  });
  check_throws<std::invalid_argument>(
      [&]() {
        server.bind("add_seven", [](const TensorNest& inputs) {
          return inputs;
        });
      },
      "duplicate RPC binding was accepted");
  server.run();

  check_throws<std::logic_error>(
      [&]() {
        server.bind("late", [](const TensorNest& inputs) {
          return inputs;
        });
      },
      "late RPC binding was accepted");
  check_throws<std::logic_error>(
      [&]() { server.run(); },
      "server was allowed to run twice");

  try {
    postman::Client client(server_address(server));
    const TensorNest inputs(at::zeros({2}, at::kFloat));
    check_throws<postman::ConnectionError>(
        [&]() { (void)client.call("add_seven", inputs); },
        "unconnected client accepted a call");
    client.connect(3);
    check_throws<postman::ConnectionError>(
        [&]() { client.connect(3); },
        "client was allowed to reconnect");
    check_throws<postman::CallError>(
        [&]() { (void)client.call("missing", inputs); },
        "unknown function did not return CallError");

    check_tensor(
        client.call("add_seven", inputs).front(),
        at::full({2}, 7, at::kFloat),
        "synchronous call returned the wrong tensor");

    const at::Tensor large = at::zeros(
        {2 * 1024 * 1024}, at::kFloat);
    check_tensor(
        client.call("add_seven", TensorNest(large)).front(),
        large + 7,
        "response above gRPC's default 4 MiB limit failed");
    client.close();
    client.close();
    check_throws<postman::ConnectionError>(
        [&]() { (void)client.call("add_seven", inputs); },
        "closed client accepted a call");
  } catch (...) {
    server.stop();
    throw;
  }
  server.stop();
  server.stop();
}

void test_async_rpc() {
  postman::Server server("127.0.0.1:0");
  server.bind("increment", [](const TensorNest& inputs) {
    return inputs.map(
        [](const at::Tensor& tensor) { return tensor + 1; });
  });
  server.bind("fail", [](const TensorNest&) -> TensorNest {
    throw std::runtime_error("ValueError: expected failure");
  });
  server.run();

  try {
    const std::string address = server_address(server);
    auto streams =
        postman::AsyncClient(address).connect(3);

    std::vector<std::future<TensorNest>> futures;
    for (int value = 0; value < 32; ++value) {
      futures.push_back(streams->call(
          "increment", TensorNest(at::tensor(value))));
    }
    streams->call(
        "increment", TensorNest(at::tensor(100)));

    for (int value = 0; value < 32; ++value) {
      check(
          futures[static_cast<std::size_t>(value)]
                  .wait_for(3s) ==
              std::future_status::ready,
          "asynchronous call timed out");
      check_tensor(
          futures[static_cast<std::size_t>(value)].get().front(),
          at::tensor(value + 1),
          "asynchronous call returned the wrong tensor");
    }

    auto failed = streams->call(
        "fail", TensorNest(std::vector<TensorNest>{}));
    check_throws<postman::CallError>(
        [&]() { (void)failed.get(); },
        "asynchronous remote error lost its CallError type");

    postman::AsyncClient reusable_client(address);
    auto first_streams = reusable_client.connect(3);
    auto second_streams = reusable_client.connect(3);
    check_tensor(
        first_streams
            ->call("increment", TensorNest(at::tensor(1)))
            .get()
            .front(),
        at::tensor(2),
        "first reconnect stream lost ownership");
    check_tensor(
        second_streams
            ->call("increment", TensorNest(at::tensor(2)))
            .get()
            .front(),
        at::tensor(3),
        "second reconnect stream failed");

    streams->close();
    check_throws<postman::ConnectionError>(
        [&]() {
          (void)streams->call(
              "increment", TensorNest(at::tensor(1)));
        },
        "closed async streams accepted a call");
    first_streams->close();
    second_streams->close();
  } catch (...) {
    server.stop();
    throw;
  }
  server.stop();
}

void test_sync_rpc_close_cancels_blocked_call() {
  std::promise<void> call_started_promise;
  std::future<void> call_started =
      call_started_promise.get_future();
  std::promise<void> release_call_promise;
  std::shared_future<void> release_call =
      release_call_promise.get_future().share();

  postman::Server server("127.0.0.1:0");
  server.bind(
      "block",
      [&](const TensorNest& inputs) {
        call_started_promise.set_value();
        release_call.wait();
        return inputs;
      });
  server.run();

  postman::Client client(server_address(server));
  client.connect(3);
  auto result = std::async(std::launch::async, [&]() {
    return client.call(
        "block", TensorNest(at::tensor(1)));
  });

  const bool started =
      call_started.wait_for(2s) == std::future_status::ready;
  auto close_result = std::async(
      std::launch::async, [&]() { client.close(); });
  const bool close_was_prompt =
      close_result.wait_for(2s) == std::future_status::ready;
  const bool call_was_cancelled_promptly =
      result.wait_for(2s) == std::future_status::ready;

  release_call_promise.set_value();
  close_result.wait();
  close_result.get();
  result.wait();
  bool call_raised_connection_error = false;
  try {
    (void)result.get();
  } catch (const postman::ConnectionError&) {
    call_raised_connection_error = true;
  }
  server.stop();

  check(started, "blocked synchronous RPC never reached the server");
  check(
      close_was_prompt,
      "Client.close() waited for the blocked server callback");
  check(
      call_was_cancelled_promptly,
      "Client.close() did not promptly unblock Client.call()");
  check(
      call_raised_connection_error,
      "cancelled synchronous call did not raise ConnectionError");
}

void test_async_rpc_capacity_and_close_cancellation() {
  std::promise<void> call_started_promise;
  std::future<void> call_started =
      call_started_promise.get_future();
  std::promise<void> release_call_promise;
  std::shared_future<void> release_call =
      release_call_promise.get_future().share();

  postman::Server server("127.0.0.1:0");
  server.bind(
      "block",
      [&](const TensorNest& inputs) {
        call_started_promise.set_value();
        release_call.wait();
        return inputs;
      });
  server.run();

  auto streams =
      postman::AsyncClient(server_address(server), 1, 2).connect(3);
  std::future<TensorNest> active = streams->call(
      "block", TensorNest(at::tensor(1)));
  const bool started =
      call_started.wait_for(2s) == std::future_status::ready;
  std::future<TensorNest> pending = streams->call(
      "block", TensorNest(at::tensor(2)));

  bool capacity_was_rejected = false;
  try {
    (void)streams->call(
        "block", TensorNest(at::tensor(3)));
  } catch (const postman::ConnectionError&) {
    capacity_was_rejected = true;
  }

  auto close_result = std::async(
      std::launch::async, [&]() { streams->close(); });
  const bool close_was_prompt =
      close_result.wait_for(2s) == std::future_status::ready;
  const bool active_was_cancelled_promptly =
      active.wait_for(2s) == std::future_status::ready;
  const bool pending_was_rejected_promptly =
      pending.wait_for(2s) == std::future_status::ready;

  release_call_promise.set_value();
  close_result.wait();
  close_result.get();

  bool active_raised_connection_error = false;
  try {
    (void)active.get();
  } catch (const postman::ConnectionError&) {
    active_raised_connection_error = true;
  }
  bool pending_raised_connection_error = false;
  try {
    (void)pending.get();
  } catch (const postman::ConnectionError&) {
    pending_raised_connection_error = true;
  }
  bool closed_was_rejected = false;
  try {
    (void)streams->call(
        "block", TensorNest(at::tensor(4)));
  } catch (const postman::ConnectionError&) {
    closed_was_rejected = true;
  }
  server.stop();

  check(started, "bounded asynchronous RPC never reached the server");
  check(
      capacity_was_rejected,
      "asynchronous client accepted work above its configured capacity");
  check(
      close_was_prompt,
      "Streams.close() waited for the blocked server callback");
  check(
      active_was_cancelled_promptly &&
          active_raised_connection_error,
      "Streams.close() did not cancel the active RPC");
  check(
      pending_was_rejected_promptly &&
          pending_raised_connection_error,
      "Streams.close() did not reject queued RPC work");
  check(
      closed_was_rejected,
      "closed asynchronous streams accepted new work");
}

void test_server_computation_queue() {
  postman::Server server("127.0.0.1:0");
  auto queue =
      std::make_shared<postman::ComputationQueue>(1);
  server.bind_queue("add_forty_two", queue);
  server.run();

  std::exception_ptr worker_error;
  std::thread worker([&]() {
    try {
      auto computation = queue->get(true);
      TensorNest inputs = computation->get_inputs();
      computation->set_outputs(inputs.map(
          [](const at::Tensor& tensor) {
            return tensor + 42;
          }));
    } catch (...) {
      worker_error = std::current_exception();
    }
  });

  try {
    postman::Client client(server_address(server));
    client.connect(3);
    check_tensor(
        client
            .call(
                "add_forty_two",
                TensorNest(at::zeros({1}, at::kFloat)))
            .front(),
        at::full({1}, 42, at::kFloat),
        "queued call returned the wrong tensor");
    client.close();
  } catch (...) {
    queue->close();
    server.stop();
    worker.join();
    throw;
  }

  queue->close();
  server.stop();
  worker.join();
  if (worker_error) {
    std::rethrow_exception(worker_error);
  }
}

}  // namespace

int main() {
  const std::vector<
      std::pair<std::string, std::function<void()>>>
      tests = {
          {"queue_and_counter", test_queue_and_counter},
          {"serialization", test_serialization},
          {"computation_queue", test_computation_queue},
          {"sync_rpc", test_sync_rpc},
          {"sync_rpc_close_cancels_blocked_call",
           test_sync_rpc_close_cancels_blocked_call},
          {"async_rpc", test_async_rpc},
          {"async_rpc_capacity_and_close_cancellation",
           test_async_rpc_capacity_and_close_cancellation},
          {"server_computation_queue",
           test_server_computation_queue},
      };

  try {
    for (const auto& [name, test] : tests) {
      test();
      std::cout << "PASS " << name << '\n';
    }
  } catch (const std::exception& error) {
    std::cerr << "postman native test failed: "
              << error.what() << '\n';
    return 1;
  }
  std::cout << "postman native tests passed\n";
  return 0;
}
