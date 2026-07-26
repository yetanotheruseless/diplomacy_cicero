/*
Copyright (c) Meta Platforms, Inc. and affiliates.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
*/
#include "postman/serialization.h"

#include <cstring>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>
#include <variant>
#include <vector>

namespace postman::detail {
namespace {

template <typename T, typename Function>
void fill_proto_from_nest(
    postman::ArrayNest* nest_pb,
    const nest::Nest<T>& value,
    Function fill_array_proto) {
  using Nest = nest::Nest<T>;
  std::visit(
      nest::overloaded{
          [&](const T& leaf) {
            nest_pb->set_kind(postman::ArrayNest::ARRAY);
            fill_array_proto(nest_pb->mutable_array(), leaf);
          },
          [&](const std::vector<Nest>& vector) {
            nest_pb->set_kind(postman::ArrayNest::VECTOR);
            for (const Nest& child : vector) {
              fill_proto_from_nest(
                  nest_pb->add_vector(), child, fill_array_proto);
            }
          },
          [&](const std::map<std::string, Nest>& map) {
            nest_pb->set_kind(postman::ArrayNest::MAP);
            auto* map_pb = nest_pb->mutable_map();
            for (const auto& [key, child] : map) {
              fill_proto_from_nest(
                  &(*map_pb)[key], child, fill_array_proto);
            }
          }},
      value.value);
}

template <typename Function>
nest::Nest<
    std::invoke_result_t<Function, const postman::NDArray&>>
nest_proto_to_nest(
    const postman::ArrayNest& nest_pb,
    Function array_proto_to_value) {
  using T = std::invoke_result_t<Function, const postman::NDArray&>;
  using Nest = nest::Nest<T>;

  if (!nest_pb.has_kind()) {
    throw std::runtime_error("ArrayNest is missing its required kind");
  }

  switch (nest_pb.kind()) {
    case postman::ArrayNest::ARRAY:
      if (!nest_pb.has_array() || nest_pb.vector_size() != 0 ||
          nest_pb.map_size() != 0) {
        throw std::runtime_error("Malformed array-valued ArrayNest");
      }
      return Nest(array_proto_to_value(nest_pb.array()));
    case postman::ArrayNest::VECTOR: {
      if (nest_pb.has_array() || nest_pb.map_size() != 0) {
        throw std::runtime_error("Malformed vector-valued ArrayNest");
      }
      std::vector<Nest> vector;
      vector.reserve(static_cast<std::size_t>(nest_pb.vector_size()));
      for (const auto& child : nest_pb.vector()) {
        vector.emplace_back(nest_proto_to_nest(child, array_proto_to_value));
      }
      return Nest(std::move(vector));
    }
    case postman::ArrayNest::MAP: {
      if (nest_pb.has_array() || nest_pb.vector_size() != 0) {
        throw std::runtime_error("Malformed map-valued ArrayNest");
      }
      std::map<std::string, Nest> map;
      for (const auto& [key, child] : nest_pb.map()) {
        map.emplace(key, nest_proto_to_nest(child, array_proto_to_value));
      }
      return Nest(std::move(map));
    }
    default:
      throw std::runtime_error(
          "ArrayNest contains an unknown kind value: " +
          std::to_string(static_cast<int>(nest_pb.kind())));
  }
}

at::Tensor materialize_cpu_tensor(const at::Tensor& tensor) {
  if (!tensor.defined()) {
    throw std::invalid_argument("Cannot serialize an undefined tensor");
  }
  if (tensor.is_meta()) {
    throw std::invalid_argument("Cannot serialize a meta tensor");
  }
  if (tensor.layout() != c10::kStrided) {
    throw std::invalid_argument(
        "Postman only serializes strided tensors; received layout " +
        std::string(c10::toString(tensor.layout())));
  }

  at::Tensor materialized = tensor.resolve_conj().resolve_neg();
  if (!materialized.device().is_cpu()) {
    materialized = materialized.to(at::kCPU);
  }
  if (!materialized.is_contiguous()) {
    materialized = materialized.contiguous();
  }
  return materialized;
}

void fill_array_proto_from_tensor(
    postman::NDArray* array,
    const at::Tensor& tensor) {
  const at::Tensor materialized = materialize_cpu_tensor(tensor);
  const std::size_t byte_count = materialized.nbytes();
  if (byte_count > static_cast<std::size_t>(kMaxMessageBytes)) {
    throw std::invalid_argument(
        "Tensor payload exceeds Postman's 512 MiB message limit");
  }

  array->set_scalar_type(static_cast<int>(materialized.scalar_type()));
  for (const std::int64_t dimension : materialized.sizes()) {
    array->add_shape(dimension);
  }

  if (byte_count == 0) {
    array->set_data("");
  } else {
    array->set_data(materialized.const_data_ptr(), byte_count);
  }
}

std::size_t expected_byte_count(
    const postman::NDArray& array_pb,
    at::ScalarType scalar_type,
    std::vector<std::int64_t>* shape) {
  constexpr int kMaxTensorDimensions = 64;
  constexpr std::int64_t kMaxDimension =
      std::numeric_limits<std::int32_t>::max();

  if (array_pb.shape_size() > kMaxTensorDimensions) {
    throw std::runtime_error(
        "Tensor payload has more than 64 dimensions");
  }

  std::size_t numel = 1;
  bool has_zero_dimension = false;
  shape->reserve(static_cast<std::size_t>(array_pb.shape_size()));
  for (const std::int64_t dimension : array_pb.shape()) {
    if (dimension < 0) {
      throw std::runtime_error("Tensor payload has a negative dimension");
    }
    if (dimension > kMaxDimension) {
      throw std::runtime_error(
          "Tensor payload dimension exceeds the supported range");
    }
    shape->push_back(dimension);
    if (dimension == 0) {
      has_zero_dimension = true;
      numel = 0;
      continue;
    }
    if (!has_zero_dimension) {
      const auto unsigned_dimension = static_cast<std::size_t>(dimension);
      if (numel > std::numeric_limits<std::size_t>::max() /
              unsigned_dimension) {
        throw std::runtime_error("Tensor element count overflows size_t");
      }
      numel *= unsigned_dimension;
    }
  }

  const std::size_t element_size = c10::elementSize(scalar_type);
  if (numel > std::numeric_limits<std::size_t>::max() / element_size) {
    throw std::runtime_error("Tensor byte count overflows size_t");
  }
  const std::size_t byte_count = numel * element_size;
  if (byte_count > static_cast<std::size_t>(kMaxMessageBytes)) {
    throw std::runtime_error(
        "Tensor payload exceeds Postman's 512 MiB message limit");
  }
  return byte_count;
}

at::Tensor tensor_from_proto(const postman::NDArray& array_pb) {
  if (!array_pb.has_scalar_type()) {
    throw std::runtime_error("Tensor payload is missing scalar_type");
  }
  if (!array_pb.has_data()) {
    throw std::runtime_error("Tensor payload is missing data");
  }

  const int scalar_type_value = array_pb.scalar_type();
  if (scalar_type_value < 0 ||
      scalar_type_value >=
          static_cast<int>(at::ScalarType::Undefined)) {
    throw std::runtime_error(
        "Tensor payload has an unsupported scalar_type: " +
        std::to_string(scalar_type_value));
  }
  const auto scalar_type =
      static_cast<at::ScalarType>(scalar_type_value);

  std::vector<std::int64_t> shape;
  const std::size_t byte_count =
      expected_byte_count(array_pb, scalar_type, &shape);
  if (array_pb.data().size() != byte_count) {
    throw std::runtime_error(
        "Tensor payload byte count does not match its shape and dtype: " +
        std::to_string(array_pb.data().size()) + " != " +
        std::to_string(byte_count));
  }

  at::Tensor tensor;
  try {
    tensor = at::empty(
        shape,
        at::TensorOptions().dtype(scalar_type).device(at::kCPU));
  } catch (const std::exception& error) {
    throw std::runtime_error(
        "Unable to allocate tensor payload with scalar_type " +
        std::to_string(scalar_type_value) + ": " + error.what());
  }
  if (byte_count != 0) {
    std::memcpy(
        tensor.mutable_data_ptr(), array_pb.data().data(), byte_count);
  }
  return tensor;
}

}  // namespace

void fill_proto_from_tensornest(
    postman::ArrayNest* nest_pb,
    const TensorNest& value) {
  if (nest_pb == nullptr) {
    throw std::invalid_argument("ArrayNest output pointer must not be null");
  }
  nest_pb->Clear();
  fill_proto_from_nest(nest_pb, value, fill_array_proto_from_tensor);
}

TensorNest nest_proto_to_tensornest(
    const postman::ArrayNest& nest_pb) {
  return nest_proto_to_nest(nest_pb, tensor_from_proto);
}

}  // namespace postman::detail
