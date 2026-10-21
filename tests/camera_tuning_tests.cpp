#include "camera_tuning.h"
#include <cassert>

int main() {
  using namespace pinyon_shift::camera;
  const Tuning data = {1, 2, 3, 4, 5, 0.1f, 10000, 60, 8, 4, 1, 2, 16, 8};
  assert(Adjust(data, 0, 0, 1, 1) == data);
  const auto edited = Adjust(data, 1, 2, 1.2f, 2);
  assert(edited[0] == data[0] + 1 && edited[3] == data[3] + 1 && edited[4] == data[4] + 1);
  assert(edited[1] == data[1] + 2 && edited[7] == data[7] * 1.2f);
  assert(edited[8] == 16 && edited[12] == 32);
  assert(std::abs(edited[9] * edited[9] / edited[8] - data[9] * data[9] / data[8]) < 0.00001f);
  for (const auto n : {2, 5, 6, 10, 11}) assert(edited[n] == data[n]);
  // Arbitrary merged/per-build data is the baseline, never hard-coded disc defaults.
  auto custom = data;
  custom[7] = 53;
  assert(Adjust(custom, 0, 0, 1, 1) == custom);
  Offset position;
  assert(position.Apply(0.9f, 1) == 1.9f);
  assert(position.Apply(1.9f, 1) == 1.9f);  // No accumulating the offset.
  assert(position.Apply(1.9f, 0) == 0.9f);  // Exact restore.
  assert(position.Apply(2.5f, 1) == 3.5f);  // A new car's own override.
  assert(position.Apply(3.5f, 0) == 2.5f);
}
