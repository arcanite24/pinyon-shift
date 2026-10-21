#include "ui/frame_inspector.h"

#include <algorithm>
#include <cstdio>

#include <imgui.h>
#include <rex/cvar.h>
#include <rex/filesystem.h>

namespace pinyon_shift::ui {
using namespace rex::graphics;

FrameInspector::FrameInspector(rex::ui::ImGuiDrawer &imgui,
                               rex::ui::ImmediateDrawer &drawer,
                               rex::system::IGraphicsSystem &graphics,
                               bool replay)
    : ImGuiDialog(&imgui), drawer_(drawer), graphics_(graphics),
      mailbox_(graphics.frame_inspector()), replay_(replay) {
  const auto path = rex::cvar::GetFlagByName("fh1_frame_replay");
  std::snprintf(dump_path_, sizeof(dump_path_), "%s", path.c_str());
  const auto view = rex::cvar::GetFlagByName("fh1_frame_inspector_view");
  view_ = view == "2" ? 2 : view == "1" ? 1 : 0;
}

FrameInspector::~FrameInspector() {
  if (mailbox_)
    mailbox_->Clear();
}

void FrameInspector::Preview(const Fh1InspectionImage &image, size_t index) {
  if (!image.error.empty()) {
    ImGui::TextWrapped("Preview unavailable: %s", image.error.c_str());
    return;
  }
  if (image.rgba.empty())
    return;
  auto &texture = textures_[index];
  if (!texture)
    texture = drawer_.CreateTexture(image.width, image.height,
                                    rex::ui::ImmediateTextureFilter::kNearest,
                                    false, image.rgba.data());
  if (!texture) {
    ImGui::TextUnformatted("Cannot upload preview texture");
    return;
  }
  const auto available = ImGui::GetContentRegionAvail();
  const float scale = std::max(
      0.1f, std::min(available.x / image.width,
                     std::max(64.0f, available.y - 40) / image.height));
  ImGui::Image(reinterpret_cast<ImTextureID>(texture.get()),
               ImVec2(image.width * scale, image.height * scale));
  if (ImGui::IsItemHovered())
    ImGui::SetTooltip(
        "%u x %u preview; nearest sample 0; RGB clamped to [0, 1]", image.width,
        image.height);
}

void FrameInspector::OnDraw(ImGuiIO &io) {
  ImGui::SetNextWindowPos(ImVec2(io.DisplaySize.x * 0.5f, io.DisplaySize.y * 0.5f),
                          ImGuiCond_FirstUseEver, ImVec2(0.5f, 0.5f));
  ImGui::SetNextWindowSize(ImVec2(std::min(1100.0f, io.DisplaySize.x * 0.94f),
                                  std::min(700.0f, io.DisplaySize.y * 0.94f)),
                           ImGuiCond_FirstUseEver);
  if (ImGui::Begin("Frame inspector", &open_) && open_) {
    if (!mailbox_) {
      ImGui::TextWrapped(
          "Frame inspection requires the desktop Vulkan native renderer.");
    } else {
      if (!mailbox_->capabilities().available)
        ImGui::TextWrapped(
            "The native executor is not ready for frame inspection.");
      if (auto current = mailbox_->snapshot(); current != snapshot_) {
        snapshot_ = std::move(current);
        textures_.clear();
        if (snapshot_)
          textures_.resize(snapshot_->surfaces.size() +
                           snapshot_->resolves.size());
        selected_surface_ = selected_resolve_ = 0;
      }
      if (replay_) {
        ImGui::TextUnformatted("Replay workspace - title suspended");
        ImGui::SetNextItemWidth(-145);
        ImGui::InputTextWithHint("##dump", "Path to a .fh1frame dump",
                                 dump_path_, sizeof(dump_path_));
        ImGui::SameLine();
        ImGui::BeginDisabled(mailbox_->busy() || !dump_path_[0] ||
                             !mailbox_->capabilities().available);
        if (ImGui::Button("Open dump")) {
          message_ = graphics_.OpenInspectionDump(rex::to_path(dump_path_),
                                                  Fh1InspectionView(view_))
                         ? ""
                         : "Could not queue replay. Use the desktop Vulkan "
                           "native renderer.";
        }
        ImGui::EndDisabled();
        const auto caps = mailbox_->capabilities();
        ImGui::RadioButton("Color", &view_, 0);
        ImGui::SameLine();
        ImGui::BeginDisabled(!caps.wireframe);
        ImGui::RadioButton("Wireframe", &view_, 1);
        ImGui::EndDisabled();
        if (!caps.wireframe &&
            ImGui::IsItemHovered(ImGuiHoveredFlags_AllowWhenDisabled))
          ImGui::SetTooltip("The device does not enable fillModeNonSolid");
        ImGui::SameLine();
        ImGui::BeginDisabled(!caps.overdraw);
        ImGui::RadioButton("Overdraw", &view_, 2);
        ImGui::EndDisabled();
        if (!caps.overdraw &&
            ImGui::IsItemHovered(ImGuiHoveredFlags_AllowWhenDisabled))
          ImGui::SetTooltip(
              "The device does not support independent attachment blending");
        ImGui::TextWrapped(
            "Select a view, then Open dump. Overdraw adds red per fragment (32 "
            "reaches 1), "
            "ignores depth and stencil tests, and retains render-pass clears.");
      } else {
        ImGui::BeginDisabled(mailbox_->busy() ||
                             !mailbox_->capabilities().available);
        if (ImGui::Button("Capture next frame"))
          mailbox_->Request(Fh1InspectionView::kColor);
        ImGui::EndDisabled();
        ImGui::SameLine();
        ImGui::TextUnformatted(mailbox_->busy()
                                   ? "Waiting for a complete frame..."
                                   : "Live capture");
        ImGui::TextWrapped("To open dumps and diagnostic views, restart with "
                           "--fh1_frame_inspector_replay=true. The title stays "
                           "suspended in that workspace.");
      }
      const auto status = mailbox_->status();
      if (!status.empty())
        ImGui::TextWrapped("%s", status.c_str());
      if (!message_.empty())
        ImGui::TextWrapped("%s", message_.c_str());
      ImGui::Separator();
      if (!snapshot_) {
        ImGui::TextWrapped(replay_ ? "Open a local frame dump to inspect its "
                                     "surfaces and resolve sources."
                                   : "Capture a frame to freeze its surfaces, "
                                     "resolve sources and texture identities.");
      } else {
        ImGui::Text(
            "%s | Frame %llu | %zu surfaces | %zu resolve sources | %zu textures",
            snapshot_->view == Fh1InspectionView::kWireframe ? "Wireframe" :
            snapshot_->view == Fh1InspectionView::kOverdraw ? "Overdraw" : "Color",
            static_cast<unsigned long long>(snapshot_->frame),
            snapshot_->surfaces.size(), snapshot_->resolves.size(),
            snapshot_->textures.size());
        if (snapshot_->truncated)
          ImGui::TextWrapped(
              "Capture limit reached: additional entries or previews may be omitted.");
        if (ImGui::BeginTabBar("inspection")) {
          if (ImGui::BeginTabItem("Surfaces")) {
            ImGui::BeginChild(
                "surface-list",
                ImVec2(ImGui::GetContentRegionAvail().x * 0.53f, 0), true);
            if (ImGui::BeginTable("surfaces", 5,
                                  ImGuiTableFlags_RowBg |
                                      ImGuiTableFlags_ScrollY)) {
              for (const char *label :
                   {"EDRAM / pitch", "Size", "Format", "Samples", "Draws"})
                ImGui::TableSetupColumn(label);
              ImGui::TableHeadersRow();
              for (int i = 0; i < int(snapshot_->surfaces.size()); ++i) {
                const auto &s = snapshot_->surfaces[i];
                ImGui::TableNextRow();
                ImGui::TableNextColumn();
                char label[80];
                std::snprintf(label, sizeof(label), "%u / %u##s%d", s.base,
                              s.pitch, i);
                if (ImGui::Selectable(label, i == selected_surface_,
                                      ImGuiSelectableFlags_SpanAllColumns))
                  selected_surface_ = i;
                if (ImGui::IsItemHovered())
                  ImGui::SetTooltip(
                      "Surface key %08X; EDRAM base and pitch in tiles", s.key);
                ImGui::TableNextColumn();
                ImGui::Text("%ux%u", s.width, s.height);
                ImGui::TableNextColumn();
                ImGui::Text("%s%u", s.depth ? "depth " : "color ", s.format);
                if (ImGui::IsItemHovered())
                  ImGui::SetTooltip("%s", s.format_name.c_str());
                ImGui::TableNextColumn();
                ImGui::Text("%u", s.samples);
                ImGui::TableNextColumn();
                ImGui::Text("%u", s.draws);
              }
              ImGui::EndTable();
            }
            ImGui::EndChild();
            ImGui::SameLine();
            ImGui::BeginChild("surface-preview");
            if (!snapshot_->surfaces.empty()) {
              const auto &surface = snapshot_->surfaces[selected_surface_];
              ImGui::TextUnformatted(surface.depth ? "Raw depth (grayscale)"
                                                   : "Color at frame end");
              Preview(surface.image, size_t(selected_surface_));
            }
            ImGui::EndChild();
            ImGui::EndTabItem();
          }
          if (ImGui::BeginTabItem("Resolve sources")) {
            ImGui::BeginChild(
                "resolve-list",
                ImVec2(ImGui::GetContentRegionAvail().x * 0.53f, 0), true);
            for (int i = 0; i < int(snapshot_->resolves.size()); ++i) {
              const auto &r = snapshot_->resolves[i];
              char label[120];
              std::snprintf(label, sizeof(label), "%08X + %X  %dx%d##r%d",
                            r.address, r.length, r.right - r.left,
                            r.bottom - r.top, i);
              if (ImGui::Selectable(label, i == selected_resolve_))
                selected_resolve_ = i;
              if (ImGui::IsItemHovered())
                ImGui::SetTooltip("Source %08X: (%d,%d)-(%d,%d)", r.source_key,
                                  r.left, r.top, r.right, r.bottom);
            }
            ImGui::EndChild();
            ImGui::SameLine();
            ImGui::BeginChild("resolve-preview");
            ImGui::TextWrapped(
                "Source at resolve time, before destination packing and sample "
                "selection. "
                "Resolves with several owners have one entry per source.");
            if (!snapshot_->resolves.empty())
              Preview(snapshot_->resolves[selected_resolve_].image,
                      snapshot_->surfaces.size() + size_t(selected_resolve_));
            ImGui::EndChild();
            ImGui::EndTabItem();
          }
          if (ImGui::BeginTabItem("Texture hashes")) {
            ImGui::TextWrapped("Hover a texture for its replacement hash. "
                               "GPU-written ranges have no CPU hash.");
            ImGui::BeginChild("texture-list");
            for (size_t i = 0; i < snapshot_->textures.size(); ++i) {
              const auto &t = snapshot_->textures[i];
              ImGui::Text("%08X  %ux%u  format %u", t.address, t.width,
                          t.height, t.format);
              if (ImGui::IsItemHovered()) {
                if (t.hash_valid)
                  ImGui::SetTooltip("XXH3 base-level bytes: %016llX",
                                    static_cast<unsigned long long>(t.hash));
                else
                  ImGui::SetTooltip("Hash unavailable: GPU-written, missing or "
                                    "larger than 16 MiB");
              }
            }
            ImGui::EndChild();
            ImGui::EndTabItem();
          }
          ImGui::EndTabBar();
        }
      }
    }
  }
  ImGui::End();
  if (!open_) {
    if (mailbox_)
      mailbox_->Clear();
    textures_.clear();
    snapshot_.reset();
    imgui_drawer()->RemoveDialog(this);
  }
}
} // namespace pinyon_shift::ui
