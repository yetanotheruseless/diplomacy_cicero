/*
Copyright (c) Meta Platforms, Inc. and affiliates.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
*/
#pragma once

#include <condition_variable>
#include <cstdint>
#include <deque>
#include <mutex>
#include <stdexcept>
#include <utility>

namespace postman {
struct QueueClosed : public std::runtime_error {
  using std::runtime_error::runtime_error;
};

// TODO: Consider using atomics for size?
// TODO: Consider re-adding the timeouts?
template <typename T>
class Queue {
 public:
  explicit Queue(int64_t max_size) : max_size_(max_size) {
    if (max_size <= 0) {
      throw std::invalid_argument("Queue max_size must be greater than zero");
    }
  }

  int64_t size() const {
    std::scoped_lock lock(mu_);
    return static_cast<int64_t>(deque_.size());
  }

  void enqueue(T item) {
    {
      std::unique_lock<std::mutex> lock(mu_);
      can_enqueue_.wait(
          lock, [this]() { return closed_ || deque_.size() < max_size_; });
      if (closed_) {
        throw QueueClosed("Enqueue to closed queue");
      }

      deque_.push_back(std::move(item));
    }

    can_dequeue_.notify_one();
  }

  bool try_enqueue(T item) {
    {
      std::scoped_lock lock(mu_);
      if (closed_) {
        throw QueueClosed("Enqueue to closed queue");
      }
      if (deque_.size() >= max_size_) {
        return false;
      }
      deque_.push_back(std::move(item));
    }

    can_dequeue_.notify_one();
    return true;
  }

  T dequeue() {
    T item = [&]() {
      std::unique_lock<std::mutex> lock(mu_);
      can_dequeue_.wait(lock, [this]() { return closed_ || !deque_.empty(); });

      if (closed_) throw QueueClosed("Dequeue from closed queue");

      T item = std::move(deque_.front());
      deque_.pop_front();
      return item;
    }();
    can_enqueue_.notify_one();
    return item;
  }

  bool is_closed() const {
    std::scoped_lock lock(mu_);
    return closed_;
  }

  std::deque<T> close() noexcept {
    std::deque<T> items;
    {
      std::scoped_lock lock(mu_);
      if (closed_) {
        return items;
      }
      closed_ = true;
      items = std::move(deque_);
    }
    can_dequeue_.notify_all();
    can_enqueue_.notify_all();
    return items;
  }

 private:
  mutable std::mutex mu_;

  const std::size_t max_size_;

  std::condition_variable can_dequeue_;
  std::condition_variable can_enqueue_;

  bool closed_ = false /* GUARDED_BY(mu_) */;
  std::deque<T> deque_ /* GUARDED_BY(mu_) */;
};

}  // namespace postman
