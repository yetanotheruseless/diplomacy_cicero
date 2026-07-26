/*
Copyright (c) Meta Platforms, Inc. and affiliates.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
*/
#pragma once

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <future>
#include <limits>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <utility>
#include <vector>

#include <ATen/ATen.h>
#include <nest.h>

#include "blocking_counter.h"
#include "queue.h"

typedef nest::Nest<at::Tensor> TensorNest;

namespace postman {

class ComputationQueue {
 public:
  static constexpr std::size_t kDefaultMaxPendingBatches = 64;

  struct Computation {
    explicit Computation(std::uint32_t batch_size)
        : num_ready(batch_size),
          future(promise.get_future()),
          batch_size(batch_size) {}

    TensorNest get_inputs() { return std::move(inputs); }

    void set_outputs(TensorNest outputs) {
      std::scoped_lock lock(completion_mutex);
      if (completed) {
        throw std::logic_error(
            "Computation result was already completed");
      }
      promise.set_value(std::move(outputs));
      completed = true;
    }

    void set_exception(std::exception_ptr error) {
      std::scoped_lock lock(completion_mutex);
      if (completed) {
        return;
      }
      completed = true;
      aborted.store(true);
      promise.set_exception(std::move(error));
    }

    bool abort(std::exception_ptr error) {
      std::scoped_lock lock(completion_mutex);
      if (completed) {
        return false;
      }
      completed = true;
      aborted.store(true);
      promise.set_exception(std::move(error));
      return true;
    }

    TensorNest inputs;
    BlockingCounter num_ready;
    std::promise<TensorNest> promise;
    std::shared_future<TensorNest> future;
    std::uint32_t size = 0;
    const std::uint32_t batch_size;
    std::atomic_bool aborted = false;

   private:
    std::mutex completion_mutex;
    bool completed = false;
  };

  explicit ComputationQueue(
      std::uint32_t batch_size,
      std::size_t max_pending_batches =
          kDefaultMaxPendingBatches)
      : batch_size_(validate_batch_size(batch_size)),
        queue_(validate_max_pending_batches(
            max_pending_batches)) {}

  std::shared_future<TensorNest> compute(
      const TensorNest& args,
      std::int64_t* index) {
    if (index == nullptr) {
      throw std::invalid_argument(
          "ComputationQueue index pointer must not be null");
    }

    std::shared_ptr<Computation> computation;
    {
      std::unique_lock lock(computation_mutex_);
      if (closed_) {
        throw QueueClosed("Compute on closed queue");
      }

      if (!current_computation_) {
        auto next_computation =
            std::make_shared<Computation>(batch_size_);
        next_computation->inputs = args.map(
            [batch_size = batch_size_](const at::Tensor& tensor) {
              if (!tensor.defined()) {
                throw std::invalid_argument(
                    "ComputationQueue inputs must be defined tensors");
              }
              if (!tensor.device().is_cpu()) {
                throw std::invalid_argument(
                    "ComputationQueue inputs must be CPU tensors");
              }
              if (tensor.layout() != c10::kStrided) {
                throw std::invalid_argument(
                    "ComputationQueue inputs must use strided layout");
              }

              std::vector<std::int64_t> shape;
              shape.reserve(
                  static_cast<std::size_t>(tensor.dim()) + 1);
              shape.push_back(batch_size);
              shape.insert(
                  shape.end(),
                  tensor.sizes().begin(),
                  tensor.sizes().end());
              return at::empty(
                  shape, tensor.options().requires_grad(false));
            });

        if (!queue_.try_enqueue(next_computation)) {
          throw std::runtime_error(
              "ComputationQueue pending-batch capacity is exhausted");
        }
        current_computation_ = std::move(next_computation);
      } else {
        validate_inputs(current_computation_->inputs, args);
      }

      computation = current_computation_;
      *index = static_cast<std::int64_t>(computation->size++);
      if (computation->size == computation->batch_size) {
        current_computation_.reset();
      }
    }

    try {
      TensorNest::for_each(
          [index](at::Tensor& input, const at::Tensor& arg) {
            input[*index].copy_(arg);
          },
          computation->inputs,
          args);
    } catch (...) {
      const std::exception_ptr error = std::current_exception();
      std::uint32_t missing_slots = 0;
      {
        std::scoped_lock lock(computation_mutex_);
        if (computation->abort(error) &&
            current_computation_ == computation) {
          missing_slots =
              computation->batch_size - computation->size;
          current_computation_.reset();
        }
      }
      computation->num_ready.DecrementCount();
      if (missing_slots != 0) {
        computation->num_ready.DecrementCount(missing_slots);
      }
      std::rethrow_exception(error);
    }

    computation->num_ready.DecrementCount();
    return computation->future;
  }

  void close() noexcept {
    std::shared_ptr<Computation> current;
    std::deque<std::shared_ptr<Computation>> queued;
    std::uint32_t missing_slots = 0;
    const auto error = std::make_exception_ptr(
        QueueClosed("ComputationQueue was closed"));
    {
      std::scoped_lock lock(computation_mutex_);
      if (closed_) {
        return;
      }
      closed_ = true;
      current = std::move(current_computation_);
      if (current) {
        missing_slots = current->batch_size - current->size;
      }
      queued = queue_.close();

      if (current) {
        current->abort(error);
        if (missing_slots != 0) {
          try {
            current->num_ready.DecrementCount(missing_slots);
          } catch (...) {
            // close() is noexcept; active writers own the remaining slots.
          }
        }
      }
    }
    for (const auto& computation : queued) {
      computation->abort(error);
    }
  }

  bool closed() const {
    std::scoped_lock lock(computation_mutex_);
    return closed_;
  }

  std::shared_ptr<Computation> get(bool wait_till_full = false) {
    while (true) {
      std::shared_ptr<Computation> computation =
          queue_.dequeue();
      std::uint32_t size;
      bool owns_missing_slots = false;
      {
        std::scoped_lock lock(computation_mutex_);
        size = computation->size;
        if (!wait_till_full &&
            current_computation_ == computation) {
          current_computation_.reset();
          owns_missing_slots = true;
        }
      }

      const bool truncate =
          owns_missing_slots && size < computation->batch_size;
      if (truncate) {
        computation->num_ready.DecrementCount(
            computation->batch_size - size);
      }

      computation->num_ready.Wait();
      if (computation->aborted.load()) {
        continue;
      }

      if (truncate) {
        computation->inputs.for_each(
            [size](at::Tensor& tensor) {
              std::vector<std::int64_t> shape(
                  tensor.sizes().begin(), tensor.sizes().end());
              shape.front() = size;
              tensor.resize_(shape);
            });
      }
      return computation;
    }
  }

  void set_batch_size(std::uint32_t batch_size) {
    batch_size = validate_batch_size(batch_size);
    std::scoped_lock lock(computation_mutex_);
    if (closed_) {
      throw QueueClosed(
          "Cannot change the batch size of a closed queue");
    }
    batch_size_ = batch_size;
  }

 private:
  static std::uint32_t validate_batch_size(
      std::uint32_t batch_size) {
    if (batch_size == 0 ||
        batch_size >
            static_cast<std::uint32_t>(
                std::numeric_limits<int>::max())) {
      throw std::invalid_argument(
          "ComputationQueue batch_size must be in [1, INT_MAX]");
    }
    return batch_size;
  }

  static std::int64_t validate_max_pending_batches(
      std::size_t max_pending_batches) {
    if (max_pending_batches == 0 ||
        max_pending_batches >
            static_cast<std::size_t>(
                std::numeric_limits<std::int64_t>::max())) {
      throw std::invalid_argument(
          "ComputationQueue max_pending_batches must be in "
          "[1, INT64_MAX]");
    }
    return static_cast<std::int64_t>(max_pending_batches);
  }

  static void validate_inputs(
      TensorNest& batched,
      const TensorNest& args) {
    TensorNest::for_each(
        [](at::Tensor& input, const at::Tensor& arg) {
          if (!arg.defined()) {
            throw std::invalid_argument(
                "ComputationQueue inputs must be defined tensors");
          }
          if (!arg.device().is_cpu()) {
            throw std::invalid_argument(
                "ComputationQueue inputs must be CPU tensors");
          }
          if (arg.layout() != c10::kStrided) {
            throw std::invalid_argument(
                "ComputationQueue inputs must use strided layout");
          }
          if (input.scalar_type() != arg.scalar_type() ||
              input.device() != arg.device() ||
              input.dim() != arg.dim() + 1) {
            throw std::invalid_argument(
                "ComputationQueue input dtype, device, or rank changed "
                "within a batch");
          }
          for (std::int64_t dimension = 0;
               dimension < arg.dim();
               ++dimension) {
            if (input.size(dimension + 1) != arg.size(dimension)) {
              throw std::invalid_argument(
                  "ComputationQueue input shape changed within a batch");
            }
          }
        },
        batched,
        args);
  }

  std::uint32_t batch_size_;
  mutable std::mutex computation_mutex_;
  bool closed_ = false;
  std::shared_ptr<Computation> current_computation_;
  Queue<std::shared_ptr<Computation>> queue_;
};

}  // namespace postman
