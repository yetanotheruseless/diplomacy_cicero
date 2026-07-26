/*
Copyright (c) Meta Platforms, Inc. and affiliates.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
*/

#include "postman/asyncclient.h"

#include <chrono>
#include <exception>
#include <future>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>

#include "postman/exceptions.h"
#include "postman/serialization.h"

namespace postman {
namespace {

std::string status_message(
    const std::string& operation,
    const grpc::Status& status) {
  std::string message = operation;
  if (!status.error_message().empty()) {
    message += ": " + status.error_message();
  }
  message += " (" + std::to_string(status.error_code()) + ")";
  return message;
}

TensorNest run_call(
    const std::shared_ptr<RPC::Stub>& stub,
    grpc::ClientContext* context,
    CallRequest request) {
  std::unique_ptr<
      grpc::ClientReaderWriter<CallRequest, CallResponse>>
      stream = stub->Call(context);
  if (!stream) {
    throw ConnectionError("Unable to create an asynchronous RPC stream");
  }

  const bool write_succeeded = stream->Write(request);
  const bool writes_done_succeeded =
      write_succeeded && stream->WritesDone();

  CallResponse response;
  const bool read_succeeded =
      writes_done_succeeded && stream->Read(&response);
  const grpc::Status status = stream->Finish();

  if (!write_succeeded) {
    throw ConnectionError(status_message("RPC write failed", status));
  }
  if (!writes_done_succeeded) {
    throw ConnectionError(
        status_message("RPC half-close failed", status));
  }
  if (!status.ok()) {
    throw ConnectionError(status_message("RPC failed", status));
  }
  if (!read_succeeded) {
    throw ConnectionError("Server closed the RPC stream without a response");
  }
  if (response.has_error()) {
    throw CallError(response.error().message());
  }
  if (!response.has_outputs()) {
    throw CallError("Server returned a response without outputs");
  }
  return detail::nest_proto_to_tensornest(response.outputs());
}

}  // namespace

AsyncClient::Streams::Streams(
    std::shared_ptr<RPC::Stub> stub,
    std::size_t max_concurrent_calls,
    std::size_t max_outstanding_calls)
    : stub_(std::move(stub)),
      state_(std::make_shared<State>(max_outstanding_calls)) {
  if (!stub_) {
    throw std::invalid_argument("AsyncClient::Streams requires an RPC stub");
  }
  if (max_concurrent_calls == 0) {
    throw std::invalid_argument(
        "max_concurrent_calls must be greater than zero");
  }
  if (max_outstanding_calls < max_concurrent_calls) {
    throw std::invalid_argument(
        "max_outstanding_calls must be at least max_concurrent_calls");
  }

  workers_.reserve(max_concurrent_calls);
  try {
    for (std::size_t index = 0; index < max_concurrent_calls; ++index) {
      workers_.emplace_back(
          &Streams::worker_loop, state_, stub_);
    }
  } catch (...) {
    {
      std::scoped_lock lock(state_->mutex);
      state_->phase = Phase::kClosing;
    }
    state_->work_available.notify_all();
    for (std::thread& worker : workers_) {
      worker.join();
    }
    {
      std::scoped_lock lock(state_->mutex);
      state_->phase = Phase::kClosed;
    }
    throw;
  }
}

AsyncClient::Streams::~Streams() {
  close();
}

std::future<TensorNest> AsyncClient::Streams::call(
    const std::string& function,
    const TensorNest& inputs) {
  if (function.empty()) {
    throw std::invalid_argument("RPC function name must not be empty");
  }

  CallRequest request;
  request.set_function(function);
  detail::fill_proto_from_tensornest(
      request.mutable_inputs(), inputs);
  auto task = std::make_shared<Task>(std::move(request));
  std::future<TensorNest> future = task->promise.get_future();

  {
    std::scoped_lock lock(state_->mutex);
    if (state_->phase != Phase::kOpen) {
      throw ConnectionError("Streams are closed");
    }
    if (state_->pending.size() + state_->active.size() >=
        state_->max_outstanding_calls) {
      throw ConnectionError("Asynchronous RPC capacity is exhausted");
    }
    state_->pending.push_back(task);
  }
  state_->work_available.notify_one();
  return future;
}

void AsyncClient::Streams::close() noexcept {
  std::scoped_lock close_lock(close_mutex_);

  std::deque<std::shared_ptr<Task>> pending;
  {
    std::scoped_lock state_lock(state_->mutex);
    if (state_->phase == Phase::kClosed) {
      return;
    }
    state_->phase = Phase::kClosing;
    pending.swap(state_->pending);
    for (const auto& [unused, task] : state_->active) {
      (void)unused;
      task->context->TryCancel();
    }
  }

  for (const std::shared_ptr<Task>& task : pending) {
    reject_task(task, "Streams closed before the RPC started");
  }
  state_->work_available.notify_all();

  for (std::thread& worker : workers_) {
    if (worker.joinable()) {
      worker.join();
    }
  }
  workers_.clear();

  {
    std::scoped_lock state_lock(state_->mutex);
    state_->phase = Phase::kClosed;
  }
}

void AsyncClient::Streams::worker_loop(
    const std::shared_ptr<State>& state,
    const std::shared_ptr<RPC::Stub>& stub) {
  while (true) {
    std::shared_ptr<Task> task;
    {
      std::unique_lock lock(state->mutex);
      state->work_available.wait(lock, [&]() {
        return state->phase != Phase::kOpen ||
            !state->pending.empty();
      });
      if (state->phase != Phase::kOpen) {
        return;
      }

      task = std::move(state->pending.front());
      state->pending.pop_front();
      state->active.emplace(task->context.get(), task);
    }

    try {
      task->promise.set_value(
          run_call(stub, task->context.get(), std::move(task->request)));
    } catch (...) {
      try {
        task->promise.set_exception(std::current_exception());
      } catch (...) {
        // The task has a single worker owner. Promise failures must not kill
        // the worker or leave the active-context registry populated.
      }
    }

    {
      std::scoped_lock lock(state->mutex);
      state->active.erase(task->context.get());
    }
  }
}

void AsyncClient::Streams::reject_task(
    const std::shared_ptr<Task>& task,
    const std::string& message) noexcept {
  try {
    task->promise.set_exception(
        std::make_exception_ptr(ConnectionError(message)));
  } catch (...) {
    // Destroying an unsettled promise still makes its future ready with
    // broken_promise, so close() remains non-blocking and noexcept.
  }
}

AsyncClient::AsyncClient(
    std::string address,
    std::size_t max_concurrent_calls,
    std::size_t max_outstanding_calls)
    : address_(std::move(address)),
      max_concurrent_calls_(max_concurrent_calls),
      max_outstanding_calls_(max_outstanding_calls) {
  if (max_concurrent_calls_ == 0) {
    throw std::invalid_argument(
        "max_concurrent_calls must be greater than zero");
  }
  if (max_outstanding_calls_ < max_concurrent_calls_) {
    throw std::invalid_argument(
        "max_outstanding_calls must be at least max_concurrent_calls");
  }
}

std::shared_ptr<AsyncClient::Streams> AsyncClient::connect(
    int deadline_sec) const {
  if (deadline_sec <= 0) {
    throw std::invalid_argument(
        "AsyncClient connect deadline must be positive");
  }

  grpc::ChannelArguments channel_arguments;
  channel_arguments.SetMaxReceiveMessageSize(kMaxMessageBytes);
  channel_arguments.SetMaxSendMessageSize(kMaxMessageBytes);
  std::shared_ptr<grpc::Channel> channel = grpc::CreateCustomChannel(
      address_,
      grpc::InsecureChannelCredentials(),
      channel_arguments);

  const auto deadline =
      std::chrono::system_clock::now() +
      std::chrono::seconds(deadline_sec);
  if (!channel->WaitForConnected(deadline)) {
    throw TimeoutError(
        "WaitForConnected timed out for " + address_);
  }

  std::shared_ptr<RPC::Stub> stub = RPC::NewStub(channel);
  return std::make_shared<Streams>(
      std::move(stub),
      max_concurrent_calls_,
      max_outstanding_calls_);
}

}  // namespace postman
