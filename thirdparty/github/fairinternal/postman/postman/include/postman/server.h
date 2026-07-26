/*
Copyright (c) Meta Platforms, Inc. and affiliates.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
*/
#pragma once

#include <atomic>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <utility>

#include <grpcpp/grpcpp.h>

#include "computationqueue.h"
#include "rpc.grpc.pb.h"

namespace postman {

class Server {
  using Function =
      std::function<TensorNest(const TensorNest&)>;

  class ServiceImpl final : public RPC::Service {
   public:
    void bind(std::string name, Function function);

   private:
    grpc::Status Call(
        grpc::ServerContext* context,
        grpc::ServerReaderWriter<
            CallResponse, CallRequest>* stream) override;

    std::map<std::string, Function> functions_;
  };

 public:
  explicit Server(std::string address)
      : address_(std::move(address)) {}
  ~Server();

  Server(const Server&) = delete;
  Server& operator=(const Server&) = delete;

  void run();
  void wait();
  void stop() noexcept;

  bool running() const noexcept { return running_.load(); }
  int port() const noexcept { return port_.load(); }

  void bind(std::string name, Function function);
  void bind_queue(
      const std::string& name,
      std::shared_ptr<ComputationQueue> queue);
  void bind_queue_batched(
      const std::string& name,
      std::shared_ptr<ComputationQueue> queue);

 private:
  const std::string address_;
  ServiceImpl service_;
  mutable std::mutex state_mutex_;
  std::unique_ptr<grpc::Server> server_;
  bool started_ = false;
  std::atomic_bool running_ = false;
  std::atomic_int port_ = 0;
};

}  // namespace postman
