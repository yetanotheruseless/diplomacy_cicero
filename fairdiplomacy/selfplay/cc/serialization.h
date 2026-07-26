/*
Copyright (c) Meta Platforms, Inc. and affiliates.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
*/
#pragma once

#include <cstddef>
#include <cstdio>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "tensor_dict.h"

namespace rela {

static constexpr int kMagicNumber = 575757;
static constexpr int kMaxReplayFields = 4096;
static constexpr int kMaxReplayFieldNameBytes = 64 * 1024;
static constexpr int kMaxReplayTensorPayloadBytes = 512 * 1024 * 1024;

inline void read_bytes(void *destination, size_t size, FILE *file) {
  if (fread(destination, 1, size, file) != size) {
    throw std::runtime_error("Unexpected end of replay buffer");
  }
}

inline int read_int(FILE *file) {
  int tmp;
  read_bytes(&tmp, sizeof(tmp), file);
  return tmp;
}

inline int read_size(FILE *file, const std::string &field) {
  const int size = read_int(file);
  if (size < 0) {
    throw std::runtime_error("Invalid negative replay buffer " + field);
  }
  return size;
}

inline int read_bounded_size(FILE *file, const std::string &field,
                             int maximum) {
  const int size = read_size(file, field);
  if (size > maximum) {
    throw std::runtime_error("Replay buffer " + field +
                             " exceeds the supported limit");
  }
  return size;
}

inline size_t remaining_file_bytes(FILE *file) {
  const long position = ftell(file);
  if (position < 0 || fseek(file, 0, SEEK_END) != 0) {
    throw std::runtime_error("Unable to inspect replay buffer size");
  }
  const long end = ftell(file);
  if (end < position || fseek(file, position, SEEK_SET) != 0) {
    throw std::runtime_error("Unable to inspect replay buffer size");
  }
  return static_cast<size_t>(end - position);
}

inline void validate_available_bytes(FILE *file, int size,
                                     const std::string &field) {
  if (static_cast<size_t>(size) > remaining_file_bytes(file)) {
    throw std::runtime_error("Replay buffer " + field +
                             " exceeds the remaining file size");
  }
}

inline void write_bytes(const void *source, size_t size, FILE *file) {
  if (fwrite(source, 1, size, file) != size) {
    throw std::runtime_error("Failed to write replay buffer");
  }
}

inline void write_int(int tmp, FILE *file) {
  write_bytes(&tmp, sizeof(tmp), file);
}

inline int checked_int_size(size_t size, const std::string &field) {
  if (size > static_cast<size_t>(std::numeric_limits<int>::max())) {
    throw std::runtime_error("Replay buffer " + field + " is too large");
  }
  return static_cast<int>(size);
}

inline int checked_bounded_size(size_t size, const std::string &field,
                                int maximum) {
  const int checked_size = checked_int_size(size, field);
  if (checked_size > maximum) {
    throw std::runtime_error("Replay buffer " + field +
                             " exceeds the supported limit");
  }
  return checked_size;
}

inline void write(const std::vector<TensorDict> &elements, FILE *f) {
  if (elements.empty()) {
    throw std::runtime_error("Cannot save an empty replay buffer");
  }

  write_int(kMagicNumber, f);
  std::vector<std::string> header;
  for (const auto &p : elements[0])
    header.push_back(p.first);

  write_int(checked_bounded_size(header.size(), "header", kMaxReplayFields), f);
  for (size_t i = 0; i < header.size(); ++i) {
    write_int(checked_bounded_size(header[i].size(), "header name",
                                   kMaxReplayFieldNameBytes),
              f);
    write_bytes(header[i].data(), header[i].size(), f);
  }

  write_int(checked_int_size(elements.size(), "element count"), f);
  for (const auto &datum : elements) {
    std::vector<torch::Tensor> all_tensors;
    for (const auto &name : header) {
      all_tensors.push_back(datum.at(name));
    }
    std::ostringstream stream;
    torch::save(all_tensors, stream);
    const std::string buffer = stream.str();
    write_int(checked_bounded_size(buffer.size(), "tensor payload",
                                   kMaxReplayTensorPayloadBytes),
              f);
    write_bytes(buffer.data(), buffer.size(), f);
  }
}

inline std::vector<TensorDict> read(FILE *f, int maximum_elements) {
  if (maximum_elements < 0) {
    throw std::invalid_argument(
        "Replay buffer maximum element count cannot be negative");
  }
  std::vector<std::string> header;
  const int magic_number = read_int(f);
  if (magic_number != kMagicNumber) {
    throw std::runtime_error("Invalid replay buffer magic number");
  }
  const int header_size =
      read_bounded_size(f, "header size", kMaxReplayFields);
  std::vector<char> buffer;
  buffer.reserve(1 << 25);
  for (int i = 0; i < header_size; ++i) {
    const int sz = read_bounded_size(f, "header name size",
                                     kMaxReplayFieldNameBytes);
    validate_available_bytes(f, sz, "header name");
    buffer.resize(sz);
    read_bytes(buffer.data(), buffer.size(), f);
    header.push_back(std::string(buffer.data(), sz));
  }

  const int element_count =
      read_bounded_size(f, "element count", maximum_elements);
  std::vector<TensorDict> elements(element_count);
  for (size_t i = 0; i < elements.size(); ++i) {
    auto &tdict = elements[i];
    const int sz = read_bounded_size(f, "tensor payload size",
                                     kMaxReplayTensorPayloadBytes);
    validate_available_bytes(f, sz, "tensor payload");
    buffer.resize(sz);
    read_bytes(buffer.data(), buffer.size(), f);
    std::vector<torch::Tensor> tensor_vec;
    torch::load(tensor_vec, static_cast<const char *>(buffer.data()), sz);
    if (tensor_vec.size() != header.size()) {
      throw std::runtime_error("Replay buffer tensor count does not match its header");
    }
    for (size_t j = 0; j < header.size(); ++j) {
      tdict[header[j]] = tensor_vec[j];
    }
  }
  return elements;
}
} // namespace rela
