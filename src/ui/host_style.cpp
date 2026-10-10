#include "ui/host_style.h"

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <vector>

#include <rex/logging.h>
#include <rex/filesystem.h>

#include "platform/host_platform.h"

namespace pinyon_shift::ui {
namespace {

// Logical size of body text; the SDK scales logical units by the window DPI.
constexpr float kFontLogicalSize = 16.0f;

std::vector<std::filesystem::path> SystemFontCandidates() {
  std::vector<std::filesystem::path> candidates;
#if defined(_WIN32)
  std::filesystem::path fonts = "C:\\Windows\\Fonts";
  if (const auto windows_directory = platform::EnvironmentPath("WINDIR")) {
    fonts = *windows_directory / "Fonts";
  }
  candidates.push_back(fonts / "segoeui.ttf");
  candidates.push_back(fonts / "arial.ttf");
#elif defined(__APPLE__)
  candidates.push_back("/System/Library/Fonts/Supplemental/Arial.ttf");
  candidates.push_back("/Library/Fonts/Arial.ttf");
#elif defined(__ANDROID__)
  candidates.push_back("/system/fonts/Roboto-Regular.ttf");
  candidates.push_back("/system/fonts/RobotoStatic-Regular.ttf");
#else
  candidates.push_back("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf");
  candidates.push_back("/usr/share/fonts/TTF/DejaVuSans.ttf");
  candidates.push_back("/usr/share/fonts/dejavu/DejaVuSans.ttf");
#endif
  return candidates;
}

ImVec4 Rgb(int red, int green, int blue, float alpha = 1.0f) {
  return ImVec4(red / 255.0f, green / 255.0f, blue / 255.0f, alpha);
}

}  // namespace

void ConfigureHostFonts(ImFontAtlas* atlas, float dpi_scale) {
  if (!atlas) {
    return;
  }
  dpi_scale = std::clamp(dpi_scale, 1.0f, 4.0f);
  static const ImWchar kGlyphRanges[] = {
      0x0020, 0x024F,  // Basic Latin through Latin Extended-B
      0x0370, 0x03FF,  // Greek
      0x0400, 0x04FF,  // Cyrillic
      0x2000, 0x206F,  // General punctuation
      0x20A0, 0x20CF,  // Currency symbols
      0,
  };
  for (const auto& path : SystemFontCandidates()) {
    std::error_code error;
    if (!std::filesystem::is_regular_file(path, error)) {
      continue;
    }
    ImFontConfig config;
    config.OversampleH = 2;
    config.OversampleV = 1;
    // Rasterize at physical size and draw at logical size, so text stays
    // sharp on high-DPI displays instead of being magnified.
    ImFont* font = atlas->AddFontFromFileTTF(rex::path_to_utf8(path).c_str(),
                                             kFontLogicalSize * dpi_scale, &config,
                                             kGlyphRanges);
    if (!font) {
      continue;
    }
    font->Scale = 1.0f / dpi_scale;
    ImGui::GetIO().FontDefault = font;
    REXLOG_INFO("Host UI font {} at {} px (DPI scale {})", rex::path_to_utf8(path.filename()),
                kFontLogicalSize, dpi_scale);
    return;
  }
  REXLOG_WARN("No host UI font found; dialogs keep the SDK debug font");
}

void ConfigureHostStyle(ImGuiStyle& style, rex::ui::Style& ui_style) {
  // Festival palette: charcoal panels, white text, orange accents with a
  // magenta highlight, instead of the SDK's green debug theme.
  const ImVec4 panel = Rgb(18, 18, 22, 0.96f);
  const ImVec4 panel_raised = Rgb(34, 34, 40);
  const ImVec4 accent = Rgb(255, 106, 19);
  const ImVec4 accent_hover = Rgb(255, 140, 60);
  const ImVec4 highlight = Rgb(230, 0, 126);
  const ImVec4 text = Rgb(242, 242, 245);

  style.WindowPadding = ImVec2(16.0f, 14.0f);
  style.FramePadding = ImVec2(10.0f, 6.0f);
  style.ItemSpacing = ImVec2(10.0f, 8.0f);
  style.WindowRounding = 4.0f;
  style.FrameRounding = 3.0f;
  style.PopupRounding = 4.0f;
  style.GrabRounding = 3.0f;
  style.WindowBorderSize = 1.0f;

  auto* colors = style.Colors;
  colors[ImGuiCol_Text] = text;
  colors[ImGuiCol_TextDisabled] = Rgb(140, 140, 150);
  colors[ImGuiCol_WindowBg] = panel;
  colors[ImGuiCol_PopupBg] = panel;
  colors[ImGuiCol_Border] = Rgb(255, 106, 19, 0.55f);
  colors[ImGuiCol_FrameBg] = panel_raised;
  colors[ImGuiCol_FrameBgHovered] = Rgb(52, 52, 60);
  colors[ImGuiCol_FrameBgActive] = Rgb(64, 64, 74);
  colors[ImGuiCol_TitleBg] = Rgb(28, 28, 34);
  colors[ImGuiCol_TitleBgActive] = Rgb(40, 40, 48);
  colors[ImGuiCol_TitleBgCollapsed] = Rgb(28, 28, 34);
  colors[ImGuiCol_MenuBarBg] = Rgb(28, 28, 34);
  colors[ImGuiCol_ScrollbarBg] = Rgb(18, 18, 22, 0.6f);
  colors[ImGuiCol_ScrollbarGrab] = Rgb(80, 80, 90);
  colors[ImGuiCol_ScrollbarGrabHovered] = accent_hover;
  colors[ImGuiCol_ScrollbarGrabActive] = accent;
  colors[ImGuiCol_CheckMark] = accent;
  colors[ImGuiCol_SliderGrab] = accent;
  colors[ImGuiCol_SliderGrabActive] = highlight;
  colors[ImGuiCol_Button] = Rgb(255, 106, 19, 0.85f);
  colors[ImGuiCol_ButtonHovered] = accent_hover;
  colors[ImGuiCol_ButtonActive] = highlight;
  colors[ImGuiCol_Header] = Rgb(255, 106, 19, 0.45f);
  colors[ImGuiCol_HeaderHovered] = Rgb(255, 106, 19, 0.70f);
  colors[ImGuiCol_HeaderActive] = highlight;
  colors[ImGuiCol_Separator] = Rgb(70, 70, 80);
  colors[ImGuiCol_SeparatorHovered] = accent_hover;
  colors[ImGuiCol_SeparatorActive] = accent;
  colors[ImGuiCol_ResizeGrip] = Rgb(255, 106, 19, 0.25f);
  colors[ImGuiCol_ResizeGripHovered] = Rgb(255, 106, 19, 0.60f);
  colors[ImGuiCol_ResizeGripActive] = accent;
  colors[ImGuiCol_Tab] = panel_raised;
  colors[ImGuiCol_TabHovered] = accent_hover;
  colors[ImGuiCol_TabActive] = accent;
  colors[ImGuiCol_TabUnfocused] = panel_raised;
  colors[ImGuiCol_TabUnfocusedActive] = Rgb(255, 106, 19, 0.6f);
  colors[ImGuiCol_TextSelectedBg] = Rgb(230, 0, 126, 0.35f);
  colors[ImGuiCol_NavCursor] = highlight;
  colors[ImGuiCol_ModalWindowDimBg] = Rgb(0, 0, 0, 0.55f);

  ui_style.toast.title = accent;
  ui_style.toast.rounding = 4.0f;
  ui_style.achievements.header_text = accent;
  ui_style.achievements.unlocked_title = Rgb(255, 170, 90);
  ui_style.achievements.badge_gamerscore = accent;
  ui_style.achievements.progress_bar = accent;
  ui_style.achievements.row_unlocked_bg = Rgb(255, 106, 19, 0.18f);
}

}  // namespace pinyon_shift::ui
