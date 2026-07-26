/*
Copyright (c) Meta Platforms, Inc. and affiliates.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
*/
#pragma once

#include <memory>
#include <mutex>
#include <string>
#include <utility>

#include <ATen/ATen.h>
#include <grpcpp/grpcpp.h>
#include <nest.h>

#include "exceptions.h"
#include "rpc.grpc.pb.h"

typedef nest::Nest<at::Tensor> TensorNest;

namespace postman {

class Client {
 public:
  explicit Client(std::string address) : address_(std::move(address)) {}
  ~Client();

  Client(const Client&) = delete;
  Client& operator=(const Client&) = delete;

  void connect(int deadline_sec = 60);
  TensorNest call(
      const std::string& function,
      const TensorNest& inputs);
  void close() noexcept;

 private:
  const std::string address_;
  std::mutex state_mutex_;
  std::mutex call_mutex_;
  bool connected_once_ = false;
  bool closed_ = false;
  std::unique_ptr<RPC::Stub> stub_;
  std::shared_ptr<grpc::ClientContext> context_;
  std::unique_ptr<
      grpc::ClientReaderWriter<CallRequest, CallResponse>>
      stream_;
};

}  // namespace postman
