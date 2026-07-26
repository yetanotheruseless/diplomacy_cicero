/*
Copyright (c) Meta Platforms, Inc. and affiliates.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
*/
#pragma once

#include <condition_variable>
#include <cstddef>
#include <deque>
#include <future>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>

#include <ATen/ATen.h>
#include <grpcpp/grpcpp.h>
#include <nest.h>

#include "rpc.grpc.pb.h"

typedef nest::Nest<at::Tensor> TensorNest;

namespace postman {

class AsyncClient {
 public:
  static constexpr std::size_t kDefaultMaxOutstandingCalls = 64;
  static constexpr std::size_t kDefaultMaxConcurrentCalls =
      kDefaultMaxOutstandingCalls;

  class Streams {
   public:
    Streams(
        std::shared_ptr<RPC::Stub> stub,
        std::size_t max_concurrent_calls,
        std::size_t max_outstanding_calls);
    ~Streams();

    Streams(const Streams&) = delete;
    Streams& operator=(const Streams&) = delete;

    /// Submit one asynchronous RPC.
    ///
    /// Calls execute on a fixed worker pool. A call is rejected when the
    /// configured outstanding-call limit is reached so request floods cannot
    /// create unbounded native threads or queued tensor payloads. If a server
    /// function waits for a full batch, max_concurrent_calls must be at least
    /// that batch size. The defaults make every accepted call concurrent.
    std::future<TensorNest> call(
        const std::string& function,
        const TensorNest& inputs);

    /// Reject new calls, cancel queued and in-flight work, and join workers.
    ///
    /// This operation is thread-safe and idempotent.
    void close() noexcept;

   private:
    struct Task {
      explicit Task(CallRequest request)
          : request(std::move(request)),
            context(std::make_shared<grpc::ClientContext>()) {}

      CallRequest request;
      std::shared_ptr<grpc::ClientContext> context;
      std::promise<TensorNest> promise;
    };

    enum class Phase {
      kOpen,
      kClosing,
      kClosed,
    };

    struct State {
      std::mutex mutex;
      std::condition_variable work_available;
      Phase phase = Phase::kOpen;
      std::deque<std::shared_ptr<Task>> pending;
      std::unordered_map<
          grpc::ClientContext*, std::shared_ptr<Task>>
          active;
      const std::size_t max_outstanding_calls;

      explicit State(std::size_t max_outstanding_calls)
          : max_outstanding_calls(max_outstanding_calls) {}
    };

    static void worker_loop(
        const std::shared_ptr<State>& state,
        const std::shared_ptr<RPC::Stub>& stub);
    static void reject_task(
        const std::shared_ptr<Task>& task,
        const std::string& message) noexcept;

    std::shared_ptr<RPC::Stub> stub_;
    std::shared_ptr<State> state_;
    std::mutex close_mutex_;
    std::vector<std::thread> workers_;
  };

  explicit AsyncClient(
      std::string address,
      std::size_t max_concurrent_calls =
          kDefaultMaxConcurrentCalls,
      std::size_t max_outstanding_calls =
          kDefaultMaxOutstandingCalls);

  std::shared_ptr<Streams> connect(int deadline_sec = 60) const;

 private:
  const std::string address_;
  const std::size_t max_concurrent_calls_;
  const std::size_t max_outstanding_calls_;
};

}  // namespace postman
