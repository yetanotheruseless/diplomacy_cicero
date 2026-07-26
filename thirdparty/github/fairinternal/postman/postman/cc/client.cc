/*
Copyright (c) Meta Platforms, Inc. and affiliates.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
*/

#include "postman/client.h"

#include <chrono>
#include <memory>
#include <stdexcept>
#include <string>

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

}  // namespace

Client::~Client() {
  close();
}

void Client::connect(int deadline_sec) {
  if (deadline_sec <= 0) {
    throw std::invalid_argument(
        "Client connect deadline must be positive");
  }

  {
    std::scoped_lock lock(state_mutex_);
    if (connected_once_) {
      throw ConnectionError(
          "Client instances cannot reconnect; create a new Client");
    }
    if (closed_) {
      throw ConnectionError("Client is closed");
    }
    connected_once_ = true;
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
    std::scoped_lock lock(state_mutex_);
    closed_ = true;
    throw TimeoutError(
        "WaitForConnected timed out for " + address_);
  }

  std::unique_ptr<RPC::Stub> stub = RPC::NewStub(channel);
  auto context = std::make_shared<grpc::ClientContext>();
  std::unique_ptr<
      grpc::ClientReaderWriter<CallRequest, CallResponse>>
      stream = stub->Call(context.get());
  if (!stream) {
    std::scoped_lock lock(state_mutex_);
    closed_ = true;
    throw ConnectionError("Unable to create RPC stream");
  }

  {
    std::scoped_lock lock(state_mutex_);
    if (closed_) {
      context->TryCancel();
    } else {
      stub_ = std::move(stub);
      context_ = std::move(context);
      stream_ = std::move(stream);
      return;
    }
  }

  (void)stream->Finish();
  throw ConnectionError("Client was closed while connecting");
}

TensorNest Client::call(
    const std::string& function,
    const TensorNest& inputs) {
  if (function.empty()) {
    throw std::invalid_argument("RPC function name must not be empty");
  }

  CallRequest request;
  request.set_function(function);
  detail::fill_proto_from_tensornest(
      request.mutable_inputs(), inputs);

  std::unique_lock call_lock(call_mutex_);
  grpc::ClientReaderWriter<CallRequest, CallResponse>* stream;
  {
    std::scoped_lock state_lock(state_mutex_);
    if (!stream_ || closed_) {
      throw ConnectionError("Client is not connected");
    }
    stream = stream_.get();
  }

  if (!stream->Write(request)) {
    const grpc::Status status = stream->Finish();
    {
      std::scoped_lock state_lock(state_mutex_);
      closed_ = true;
      stream_.reset();
    }
    throw ConnectionError(status_message("RPC write failed", status));
  }

  CallResponse response;
  if (!stream->Read(&response)) {
    const grpc::Status status = stream->Finish();
    {
      std::scoped_lock state_lock(state_mutex_);
      closed_ = true;
      stream_.reset();
    }
    if (status.ok()) {
      throw ConnectionError(
          "Server closed the RPC stream without a response");
    }
    throw ConnectionError(status_message("RPC read failed", status));
  }

  if (response.has_error()) {
    throw CallError(response.error().message());
  }
  if (!response.has_outputs()) {
    throw CallError("Server returned a response without outputs");
  }
  return detail::nest_proto_to_tensornest(response.outputs());
}

void Client::close() noexcept {
  std::shared_ptr<grpc::ClientContext> context;
  {
    std::scoped_lock state_lock(state_mutex_);
    if (closed_) {
      return;
    }
    closed_ = true;
    context = context_;
  }

  if (context) {
    context->TryCancel();
  }

  std::unique_lock call_lock(call_mutex_);
  std::unique_ptr<
      grpc::ClientReaderWriter<CallRequest, CallResponse>>
      stream;
  {
    std::scoped_lock state_lock(state_mutex_);
    stream = std::move(stream_);
    context_.reset();
    stub_.reset();
  }
  if (!stream) {
    return;
  }

  (void)stream->WritesDone();
  (void)stream->Finish();
}

}  // namespace postman
