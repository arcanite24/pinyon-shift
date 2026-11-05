#pragma once

#include <cstdint>
#include <string_view>

namespace rex::ui {
class ImmediateTexture;
}

namespace pinyon_shift::hostui {

// A texture sub-rectangle in normalized coordinates.
struct UvRect {
  float u0 = 0.0f;
  float v0 = 0.0f;
  float u1 = 1.0f;
  float v1 = 1.0f;
};

constexpr uint32_t Rgba(uint32_t r, uint32_t g, uint32_t b, uint32_t a = 255) {
  return r | g << 8 | b << 16 | a << 24;
}

// `color` with its alpha scaled by `factor` (0 to 1).
constexpr uint32_t Fade(uint32_t color, float factor) {
  const float alpha = float(color >> 24) * (factor < 0.0f ? 0.0f : factor > 1.0f ? 1.0f : factor);
  return (color & 0x00FFFFFFu) | (uint32_t(alpha + 0.5f) << 24);
}

// The title's fonts: the heavy italic display face of the pause menu and the
// condensed slab of its help bar and values.
enum class Font { kDisplay, kLabel };

// How a disc texture is turned into one the painter draws.
enum class TextureMode {
  kColor,     // as the title samples it
  kMask,      // white, the shape in alpha: the colour tints it
  kLuminance, // white, alpha from brightness (sheen and glow art on black)
};

// What a painted screen (MenuScreen::set_paint) draws with. Coordinates are
// title pixels of the 1280x720 layout; the host UI scales them to the output.
class Painter {
 public:
  virtual ~Painter() = default;

  virtual void Rect(float x, float y, float width, float height, uint32_t color,
                    rex::ui::ImmediateTexture* texture = nullptr, float skew = 0.0f,
                    UvRect uv = {}) = 0;
  // Left to right.
  virtual void Gradient(float x, float y, float width, float height, uint32_t left,
                        uint32_t right, rex::ui::ImmediateTexture* texture = nullptr,
                        float skew = 0.0f, UvRect uv = {}) = 0;
  // Top to bottom.
  virtual void VerticalGradient(float x, float y, float width, float height, uint32_t top,
                                uint32_t bottom) = 0;
  virtual void Disc(float x, float y, float radius, uint32_t color) = 0;
  // Draws `text` with its left edge (align 0), centre (0.5) or right edge (1)
  // at `x`; returns its width.
  virtual float Text(Font font, float size, std::string_view text, float x, float baseline,
                     uint32_t color, float align = 0.0f) = 0;
  virtual float Measure(Font font, float size, std::string_view text) = 0;
  // Word-wrapped from `top`, at most `max_lines` lines (0: no limit, the last
  // kept line ends in "..."); returns the height used.
  virtual float Wrapped(Font font, float size, std::string_view text, float x, float top,
                        float width, uint32_t color, int max_lines = 0) = 0;
  // A texture from the title's media/ui/textures/Horizon.zip, loaded once
  // while the host UI is open; nullptr when the disc lacks it.
  virtual rex::ui::ImmediateTexture* Texture(std::string_view member,
                                             TextureMode mode = TextureMode::kColor) = 0;
  // Later draws show only inside the rectangle, until Unclip.
  virtual void Clip(float x, float y, float width, float height) = 0;
  virtual void Unclip() = 0;
  // A pointer target: the screen's pointer callback gets `target` when the
  // pointer is over the rectangle (the last one registered wins).
  virtual void Hit(int target, float x, float y, float width, float height) = 0;
  // Seconds since the screen was first painted.
  virtual float seconds() const = 0;
};

}  // namespace pinyon_shift::hostui
