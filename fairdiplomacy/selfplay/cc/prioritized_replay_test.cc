/*
Copyright (c) Meta Platforms, Inc. and affiliates.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
*/
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>

#include "prioritized_replay.h"

using buffer::NestPrioritizedReplay;
using rela::TensorDict;

namespace {

template <typename Actual, typename Expected>
void expect_equal(const Actual &actual, const Expected &expected,
                  const std::string &message) {
  if (actual != expected) {
    throw std::runtime_error(message + ": expected " +
                             std::to_string(expected) + ", got " +
                             std::to_string(actual));
  }
}

TensorDict build_data() {
  TensorDict data;

  data["observations/x_board_state"] =
      torch::zeros({128, 835}).to(torch::kLong);
  data["observations/x_build_numbers"] =
      torch::zeros({128, 7}).to(torch::kLong);
  data["observations/x_in_adj_phase"] =
      torch::zeros({128}).to(torch::kLong);
  data["observations/x_loc_idxs"] =
      torch::zeros({128, 7, 81}).to(torch::kLong);
  data["observations/x_possible_actions"] =
      torch::zeros({128, 7, 17, 469}).to(torch::kLong);
  data["observations/x_prev_orders"] =
      torch::zeros({128, 2, 100}).to(torch::kLong);
  data["observations/x_prev_state"] =
      torch::zeros({128, 835}).to(torch::kLong);
  data["observations/x_season"] =
      torch::zeros({128, 3}).to(torch::kLong);
  data["done"] = torch::zeros({128});
  data["rewards"] = torch::zeros({128, 7});
  return data;
}

void test_add_and_sample() {
  constexpr int capacity = 100;
  NestPrioritizedReplay replay(capacity, 1, 0.1F, 0.1F, 1);

  for (int i = 0; i < 10; ++i) {
    replay.add_one(build_data(), 1.0F);
  }

  auto [batch, weights] = replay.sample(10);
  auto done = batch.at("done");
  expect_equal(done.dim(), 2, "sampled done rank");
  expect_equal(done.size(0), int64_t{128}, "sampled time dimension");
  expect_equal(done.size(1), int64_t{10}, "sampled batch dimension");
  expect_equal(weights.numel(), int64_t{10}, "sampled weight count");
}

void test_add_and_sample_shuffled() {
  constexpr int capacity = 100;
  NestPrioritizedReplay replay(capacity, 1, 0.1F, 0.1F, 1,
                               /*shuffle=*/true);

  for (int i = 0; i < 10; ++i) {
    replay.add_one(build_data(), 1.0F);
  }

  auto [batch, weights] = replay.sample(10);
  auto done = batch.at("done");
  expect_equal(done.dim(), 2, "shuffled done rank");
  expect_equal(done.size(0), int64_t{1}, "shuffled time dimension");
  expect_equal(done.size(1), int64_t{1280}, "shuffled batch dimension");
  expect_equal(weights.numel(), int64_t{1280}, "shuffled weight count");
}

void test_numel_accounting() {
  constexpr int capacity = 5;
  NestPrioritizedReplay replay(capacity, 1, 0.1F, 0.1F, 1);

  int64_t numel = 0;
  int64_t first_size = -1;
  for (int i = 0; i < capacity + 1; ++i) {
    auto data = build_data();
    rela::tensor_dict::for_each(
        data, [&numel](const torch::Tensor &tensor) {
          numel += tensor.numel();
        });
    if (i == 0) {
      first_size = numel;
    }
    replay.add_one(std::move(data), 1.0F);
    expect_equal(replay.total_numel(), numel, "stored tensor elements");
  }

  replay.sample(capacity);
  expect_equal(replay.total_numel(), numel - first_size,
               "evicted tensor elements");
}

void test_byte_accounting() {
  constexpr int capacity = 5;
  NestPrioritizedReplay replay(capacity, 1, 0.1F, 0.1F, 1);

  int64_t bytes = 0;
  int64_t first_size = -1;
  for (int i = 0; i < capacity + 1; ++i) {
    auto data = build_data();
    rela::tensor_dict::for_each(data, [&bytes](const torch::Tensor &tensor) {
      bytes += tensor.numel() * tensor.element_size();
    });
    if (i == 0) {
      first_size = bytes;
    }
    replay.add_one(std::move(data), 1.0F);
    expect_equal(replay.total_bytes(), bytes, "stored tensor bytes");
  }

  replay.sample(capacity);
  expect_equal(replay.total_bytes(), bytes - first_size,
               "evicted tensor bytes");
}

void test_stack_owned_async_add() {
  NestPrioritizedReplay replay(4, 1, 1.0F, 0.0F, 0);
  auto future = replay.add_batch_async(
      {build_data(), build_data()}, torch::ones({2}, torch::kFloat32));
  future.get();
  expect_equal(replay.size(), 2, "async stack-owned replay size");
}

} // namespace

int main() {
  try {
    test_add_and_sample();
    test_add_and_sample_shuffled();
    test_numel_accounting();
    test_byte_accounting();
    test_stack_owned_async_add();
  } catch (const std::exception &error) {
    std::cerr << "prioritized_replay_test failed: " << error.what() << '\n';
    return 1;
  }
  std::cout << "prioritized_replay_test passed\n";
  return 0;
}
