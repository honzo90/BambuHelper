#include "ws43b_solid_fill.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <vector>

// Exercises the production RGB565 fill helper in ordinary host memory.
// This does not reproduce ESP32 PSRAM/cache behavior or prove LCD correctness.
namespace {
size_t checks = 0;

void expect(bool condition, const char *message) {
  ++checks;
  if (!condition) {
    std::cerr << "FAIL: " << message << '\n';
    std::exit(1);
  }
}

struct GuardedPixels {
  static constexpr size_t guardPixels = 32;
  static constexpr uint16_t guard = 0xcafe;
  std::vector<uint16_t> storage;
  const size_t count;

  explicit GuardedPixels(size_t pixels)
      : storage(pixels + 2 * guardPixels, guard), count(pixels) {
    for (size_t i = 0; i < count; ++i)
      data()[i] = uint16_t((i * 4051u) ^ (i >> 3) ^ 0xa55au);
  }
  uint16_t *data() { return storage.data() + guardPixels; }
  const uint16_t *data() const { return storage.data() + guardPixels; }
  bool guardsIntact() const {
    return std::all_of(storage.begin(), storage.begin() + guardPixels,
                       [](uint16_t pixel) { return pixel == guard; }) &&
           std::all_of(storage.end() - guardPixels, storage.end(),
                       [](uint16_t pixel) { return pixel == guard; });
  }
};

void checkRect(size_t stride, size_t height, size_t x, size_t y,
               size_t width, size_t rectHeight, uint16_t color) {
  GuardedPixels canvas(stride * height);
  const auto before = canvas.storage;
  expect(ws43b::fillSolidRectChecked(canvas.data(), stride, height, x, y,
                                    width, rectHeight, color),
         "valid solid rectangle succeeds");
  bool selectedCorrect = true, restUnchanged = true;
  for (size_t row = 0; row < height; ++row) {
    for (size_t col = 0; col < stride; ++col) {
      const size_t index = row * stride + col;
      const bool inside = row >= y && row - y < rectHeight &&
                          col >= x && col - x < width;
      if (inside) selectedCorrect &= canvas.data()[index] == color;
      else restUnchanged &= canvas.data()[index] ==
                            before[index + GuardedPixels::guardPixels];
    }
  }
  expect(selectedCorrect, "every selected pixel has the requested RGB565 value");
  expect(restUnchanged, "every pixel outside the rectangle retains its value");
  expect(canvas.guardsIntact(), "rectangle leaves both allocation guards unchanged");
}

void geometriesAndColors() {
  struct Rect { size_t stride, height, x, y, width, rectHeight; };
  constexpr Rect rectangles[] = {
      {800, 480, 0, 0, 800, 480},   // Entire physical frame.
      {800, 480, 1, 1, 798, 478},   // Odd start with a surrounding border.
      {800, 480, 24, 16, 440, 40},  // P2S title clip.
      {800, 480, 44, 128, 435, 67}, // Progress clip, odd width.
      {800, 480, 799, 479, 1, 1},   // Last addressable pixel.
      {800, 480, 0, 479, 800, 1},   // Last full row.
      {800, 480, 799, 0, 1, 480},   // Last column.
      {67, 9, 1, 2, 65, 5},        // Odd stride and odd start.
      {67, 9, 2, 2, 64, 5},        // Even start, same odd stride.
      {16, 5, 0, 0, 16, 5},        // Prior memset_multi boundary.
      {17, 5, 0, 0, 17, 5},
      {26, 3, 0, 1, 13, 1},        // Prior expanding-copy seed length.
      {26, 3, 13, 1, 13, 1},
      {3, 3, 1, 1, 1, 1},
      {1, 1, 0, 0, 1, 1},
  };
  constexpr uint16_t colors[] = {0x0000, 0xffff, 0x0843, 0xf7be,
                                  0xf800, 0x07e0, 0x001f, 0x5555};
  for (const auto &r : rectangles)
    for (uint16_t color : colors)
      checkRect(r.stride, r.height, r.x, r.y, r.width, r.rectHeight, color);
}

void successiveOverlaps() {
  constexpr size_t stride = 800, height = 480;
  GuardedPixels canvas(stride * height);
  std::vector<uint16_t> reference(canvas.data(), canvas.data() + canvas.count);
  uint32_t random = 0x1234abcdu;
  auto next = [&]() {
    random ^= random << 13;
    random ^= random >> 17;
    random ^= random << 5;
    return random;
  };
  for (unsigned n = 0; n < 64; ++n) {
    const size_t x = next() % stride, y = next() % height;
    const size_t w = 1 + next() % (stride - x);
    const size_t h = 1 + next() % (height - y);
    const uint16_t color = uint16_t(next());
    // This reference uses standard range fill on rows, not production stores.
    for (size_t row = y; row < y + h; ++row)
      std::fill(reference.begin() + row * stride + x,
                reference.begin() + row * stride + x + w, color);
    expect(ws43b::fillSolidRectChecked(canvas.data(), stride, height, x, y, w, h, color),
           "successive partly overlapping rectangle succeeds");
    expect(std::equal(reference.begin(), reference.end(), canvas.data()),
           "successive rectangle preserves all earlier pixels outside its bounds");
    expect(canvas.guardsIntact(), "successive rectangle retains allocation guards");
  }
}

void twoByteAlignment() {
  // An address aligned to two bytes but not four is valid for RGB565.
  alignas(8) std::array<uint16_t, 19> storage;
  storage.fill(0x1234);
  auto *canvas = storage.data() + 1;
  expect(reinterpret_cast<uintptr_t>(canvas) % 4 == 2,
         "fixture exercises two-byte-only alignment");
  expect(ws43b::fillSolidRectChecked(canvas, 5, 3, 1, 1, 3, 2, 0xf7be),
         "two-byte-only aligned buffer is accepted");
  for (size_t i = 0; i < storage.size(); ++i) {
    const bool inside = (i >= 7 && i < 10) || (i >= 12 && i < 15);
    expect(storage[i] == (inside ? 0xf7be : 0x1234),
           "two-byte-only fill changes precisely selected pixels");
  }
}

void emptyRectangles() {
  constexpr size_t stride = 67, height = 9;
  GuardedPixels canvas(stride * height);
  const auto before = canvas.storage;
  struct Empty { size_t x, y, w, h; };
  constexpr Empty empty[] = {
      {0, 0, 0, 0}, {1, 1, 0, 4}, {1, 1, 4, 0},
      {stride, height, 0, 0}, {stride, 0, 0, height}, {0, height, stride, 0},
  };
  for (const auto &r : empty) {
    expect(ws43b::fillSolidRectChecked(canvas.data(), stride, height,
                                      r.x, r.y, r.w, r.h, 0xffff),
           "empty rectangle at a valid origin is a successful no-op");
    expect(canvas.storage == before, "empty rectangle leaves the entire allocation unchanged");
  }
}

void invalidArguments() {
  constexpr size_t stride = 67, height = 9;
  GuardedPixels canvas(stride * height);
  const auto before = canvas.storage;
  auto reject = [&](uint16_t *pixels, size_t rowPixels, size_t rows, size_t x,
                    size_t y, size_t w, size_t h, const char *message) {
    expect(!ws43b::fillSolidRectChecked(pixels, rowPixels, rows, x, y, w, h, 0xffff), message);
    expect(canvas.storage == before, "invalid arguments leave supplied allocation untouched");
  };
  auto *p = canvas.data();
  reject(nullptr, stride, height, 0, 0, 1, 1, "reject null buffer");
  reject(nullptr, stride, height, 0, 0, 0, 0, "empty rectangle cannot bypass null validation");
  reject(p, 0, height, 0, 0, 0, 0, "reject zero stride even for an empty rectangle");
  reject(p, stride, 0, 0, 0, 0, 0, "reject zero buffer height even for an empty rectangle");
  auto *unaligned = reinterpret_cast<uint16_t *>(reinterpret_cast<uint8_t *>(p) + 1);
  reject(unaligned, stride, height, 0, 0, 1, 1, "reject odd buffer address");
  reject(unaligned, stride, height, 0, 0, 0, 0, "empty rectangle cannot bypass alignment validation");
  reject(p, stride, height, stride, 0, 1, 1, "reject nonempty rectangle starting beyond final column");
  reject(p, stride, height, 0, height, 1, 1, "reject nonempty rectangle starting beyond final row");
  reject(p, stride, height, stride + 1, 0, 0, 0, "reject empty rectangle with x beyond buffer");
  reject(p, stride, height, 0, height + 1, 0, 0, "reject empty rectangle with y beyond buffer");
  reject(p, stride, height, 1, 0, stride, 1, "reject rectangle overflowing right edge by one");
  reject(p, stride, height, 0, 1, 1, height, "reject rectangle overflowing bottom edge by one");
  reject(p, stride, height, SIZE_MAX, 0, 1, 1, "reject wrapped x coordinate before address arithmetic");
  reject(p, stride, height, 0, SIZE_MAX, 1, 1, "reject wrapped y coordinate before address arithmetic");
  reject(p, stride, height, 1, 0, SIZE_MAX, 1, "reject overflowing x plus width");
  reject(p, stride, height, 0, 1, 1, SIZE_MAX, "reject overflowing y plus height");
  reject(p, stride, height, 0, 0, 0, SIZE_MAX, "empty width cannot bypass height validation");
  reject(p, stride, height, 0, 0, SIZE_MAX, 0, "empty height cannot bypass width validation");
  reject(p, stride, height, 0, height, 0, 1, "empty width cannot extend below bottom edge");
  reject(p, stride, height, stride, 0, 1, 0, "empty height cannot extend beyond right edge");
  reject(p, SIZE_MAX, 2, 0, 0, 0, 0, "reject overflowing pixel count even for empty rectangle");
  reject(p, SIZE_MAX / 2 + 1, 1, 0, 0, 0, 0, "reject overflowing byte count even for empty rectangle");
  reject(p, 1, SIZE_MAX, 0, 0, 0, 0, "reject overflowing height times pixel size");
  auto *high = reinterpret_cast<uint16_t *>(UINTPTR_MAX & ~uintptr_t(1));
  reject(high, 1, 1, 0, 0, 0, 0, "reject buffer end-address overflow before any dereference");
  reject(high, 1, 1, 0, 0, 1, 1, "reject nonempty buffer end-address overflow before dereference");
}
} // namespace

int main() {
  geometriesAndColors();
  successiveOverlaps();
  twoByteAlignment();
  emptyRectangles();
  invalidArguments();
  std::cout << "PASS: " << checks << " native RGB565 solid-fill checks; hardware unverified\n";
}
