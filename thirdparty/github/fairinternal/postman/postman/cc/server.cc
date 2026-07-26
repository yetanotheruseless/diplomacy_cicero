/*
Copyright (c) Meta Platforms, Inc. and affiliates.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
*/

#include "postman/server.h"

#include <chrono>
#include <cstdint>
#include <exception>
#include <future>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <ATen/ATen.h>
#include <nest.h>

#include "postman/computationqueue.h"
#include "postman/exceptions.h"
#include "postman/serialization.h"

namespace postman {
namespace {

TensorNest wait_for_outputs(
    const std::shared_future<TensorNest>& future) {
  return future.get();
}

TensorNest select_output(
    const TensorNest& outputs,
    std::int64_t index) {
  return outputs.map([index](const at::Tensor& tensor) {
    if (!tensor.defined() || tensor.dim() == 0 ||
        index < 0 || index >= tensor.size(0)) {
      throw std::runtime_error(
          "Batched function output is missing the requested batch row");
    }
    return tensor[index];
  });
}

std::int64_t validate_batched_inputs(
    const TensorNest& inputs) {
  const std::vector<at::Tensor> leaves = inputs.flatten();
  if (leaves.empty()) {
    throw std::invalid_argument(
        "Batched RPC requires at least one tensor input");
  }
  if (!leaves.front().defined() ||
      leaves.front().dim() == 0) {
    throw std::invalid_argument(
        "Batched RPC inputs must have a leading batch dimension");
  }

  const std::int64_t batch_size = leaves.front().size(0);
  if (batch_size <= 0) {
    throw std::invalid_argument(
        "Batched RPC batch dimension must be greater than zero");
  }
  for (const at::Tensor& tensor : leaves) {
    if (!tensor.defined() || tensor.dim() == 0 ||
        tensor.size(0) != batch_size) {
      throw std::invalid_argument(
          "All batched RPC inputs must have the same leading dimension");
    }
  }
  return batch_size;
}

}  // namespace

void Server::ServiceImpl::bind(
    std::string name,
    Function function) {
  if (name.empty()) {
    throw std::invalid_argument(
        "RPC function name must not be empty");
  }
  if (!function) {
    throw std::invalid_argument(
        "RPC function must not be empty");
  }
  const auto [unused, inserted] =
      functions_.emplace(std::move(name), std::move(function));
  (void)unused;
  if (!inserted) {
    throw std::invalid_argument(
        "An RPC function with that name is already bound");
  }
}

grpc::Status Server::ServiceImpl::Call(
    grpc::ServerContext* context,
    grpc::ServerReaderWriter<
        CallResponse, CallRequest>* stream) {
  CallRequest request;
  while (stream->Read(&request)) {
    CallResponse response;
    try {
      if (!request.has_function() ||
          request.function().empty()) {
        throw std::invalid_argument(
            "RPC request is missing a function name");
      }
      if (!request.has_inputs()) {
        throw std::invalid_argument(
            "RPC request is missing inputs");
      }

      const auto function = functions_.find(request.function());
      if (function == functions_.end()) {
        throw std::runtime_error(
            "AttributeError: No such function '" +
            request.function() + "'");
      }
      const TensorNest result = function->second(
          detail::nest_proto_to_tensornest(request.inputs()));
      detail::fill_proto_from_tensornest(
          response.mutable_outputs(), result);
    } catch (const QueueClosed&) {
      break;
    } catch (const std::exception& error) {
      std::cerr << "Error in " << request.function() << ": "
                << error.what() << '\n';
      response.mutable_error()->set_message(error.what());
    } catch (...) {
      return grpc::Status(
          grpc::StatusCode::INTERNAL,
          "RPC function raised a non-standard exception");
    }

    if (!stream->Write(response)) {
      if (context->IsCancelled()) {
        return grpc::Status(
            grpc::StatusCode::CANCELLED,
            "Client cancelled the RPC stream");
      }
      return grpc::Status(
          grpc::StatusCode::UNAVAILABLE,
          "Unable to write the RPC response");
    }
    request.Clear();
  }

  return grpc::Status::OK;
}

Server::~Server() {
  stop();
}

void Server::run() {
  std::scoped_lock lock(state_mutex_);
  if (started_) {
    throw std::logic_error(
        "Server instances may only be run once");
  }

  grpc::ServerBuilder builder;
  builder.SetMaxReceiveMessageSize(kMaxMessageBytes);
  builder.SetMaxSendMessageSize(kMaxMessageBytes);
  builder.AddChannelArgument(GRPC_ARG_ALLOW_REUSEPORT, 0);

  int selected_port = 0;
  builder.AddListeningPort(
      address_,
      grpc::InsecureServerCredentials(),
      &selected_port);
  builder.RegisterService(&service_);

  std::unique_ptr<grpc::Server> server =
      builder.BuildAndStart();
  if (!server || selected_port == 0) {
    throw std::runtime_error(
        "Failed to start Postman server at " + address_ +
        "; the address may already be in use");
  }

  server_ = std::move(server);
  started_ = true;
  port_.store(selected_port);
  running_.store(true);
}

void Server::wait() {
  grpc::Server* server;
  {
    std::scoped_lock lock(state_mutex_);
    if (!server_) {
      throw std::logic_error("Server has not been run");
    }
    server = server_.get();
  }
  server->Wait();
}

void Server::stop() noexcept {
  grpc::Server* server;
  {
    std::scoped_lock lock(state_mutex_);
    if (!server_ || !running_.exchange(false)) {
      return;
    }
    server = server_.get();
  }
  server->Shutdown(std::chrono::system_clock::now());
}

void Server::bind(std::string name, Function function) {
  std::scoped_lock lock(state_mutex_);
  if (started_) {
    throw std::logic_error(
        "RPC functions must be bound before Server.run()");
  }
  service_.bind(std::move(name), std::move(function));
}

void Server::bind_queue(
    const std::string& name,
    std::shared_ptr<ComputationQueue> queue) {
  if (!queue) {
    throw std::invalid_argument(
        "bind_queue requires a computation queue");
  }
  bind(name, [queue = std::move(queue)](
                 const TensorNest& inputs) {
    std::int64_t index;
    const auto future = queue->compute(inputs, &index);
    return select_output(wait_for_outputs(future), index);
  });
}

void Server::bind_queue_batched(
    const std::string& name,
    std::shared_ptr<ComputationQueue> queue) {
  if (!queue) {
    throw std::invalid_argument(
        "bind_queue_batched requires a computation queue");
  }
  bind(name, [queue = std::move(queue)](
                 const TensorNest& inputs) {
    const std::int64_t batch_size =
        validate_batched_inputs(inputs);

    std::vector<std::int64_t> indices(
        static_cast<std::size_t>(batch_size));
    std::vector<std::shared_future<TensorNest>> futures;
    futures.reserve(static_cast<std::size_t>(batch_size));
    for (std::int64_t row = 0; row < batch_size; ++row) {
      futures.push_back(queue->compute(
          inputs.map([row](const at::Tensor& tensor) {
            return tensor[row];
          }),
          &indices[static_cast<std::size_t>(row)]));
    }

    std::vector<TensorNest> outputs;
    outputs.reserve(static_cast<std::size_t>(batch_size));
    for (std::int64_t row = 0; row < batch_size; ++row) {
      outputs.emplace_back(select_output(
          wait_for_outputs(
              futures[static_cast<std::size_t>(row)]),
          indices[static_cast<std::size_t>(row)]));
    }

    nest::Nest<std::vector<at::Tensor>> zipped =
        TensorNest::zip(outputs);
    return zipped.map(
        [](const std::vector<at::Tensor>& tensors) {
          return at::stack(tensors);
        });
  });
}

}  // namespace postman
