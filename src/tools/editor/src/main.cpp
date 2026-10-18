/*
 * Savior AI - Level Editor
 * Copyright (C) 2026 Savior AI Team
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

#include <QApplication>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include "DataSerializer.hpp"
#include "LevelData.hpp"
#include "MainWindow.hpp"

// CHECK5 round-trip probe (headless): load models.json -> save to a temp
// file -> reload -> byte-compare models incl. asym_patches. Detects BOTH
// the load-side and save-side drops of the optional field. Never touches
// the input file.
static int RunSelfTest(const char* modelsPath) {
    namespace fs = std::filesystem;
    std::vector<hero::ModelData> original, roundtrip;
    if (!hero::DataSerializer::LoadModelsFromFile(original, modelsPath)) {
        std::fprintf(stderr, "selftest: cannot load %s\n", modelsPath);
        return 2;
    }
    std::ifstream in(modelsPath);
    std::ostringstream ss;
    ss << in.rdbuf();
    const bool fileHasPatches =
        ss.str().find("asym_patches") != std::string::npos;
    const bool fileHasMidBand =
        ss.str().find("mid_band_type") != std::string::npos;
    int withPatches = 0;
    int withMidBand = 0;
    for (const auto& m : original) {
        if (!m.asym_patches.empty()) ++withPatches;
        if (m.mid_band_type != 0) ++withMidBand;
    }
    if (fileHasPatches && withPatches == 0) {
        std::fprintf(stderr,
                     "selftest: file contains asym_patches but the LOADER "
                     "dropped it\n");
        return 1;
    }
    if (fileHasMidBand && withMidBand == 0) {
        std::fprintf(stderr,
                     "selftest: file contains mid_band_type but the LOADER "
                     "dropped it\n");
        return 1;
    }
    const fs::path tmp =
        fs::temp_directory_path() / "savior_editor_selftest_models.json";
    if (!hero::DataSerializer::SaveModelsToFile(original, tmp.string())) {
        std::fprintf(stderr, "selftest: save to temp failed\n");
        return 2;
    }
    if (!hero::DataSerializer::LoadModelsFromFile(roundtrip, tmp.string())) {
        std::fprintf(stderr, "selftest: reload from temp failed\n");
        return 2;
    }
    fs::remove(tmp);
    if (original.size() != roundtrip.size()) {
        std::fprintf(stderr, "selftest: model count %zu -> %zu\n",
                     original.size(), roundtrip.size());
        return 1;
    }
    for (size_t i = 0; i < original.size(); ++i) {
        const auto& a = original[i];
        const auto& b = roundtrip[i];
        if (a.id != b.id || a.name != b.name || a.width != b.width ||
            a.height != b.height || a.tiles != b.tiles) {
            std::fprintf(stderr, "selftest: model %d base fields changed\n",
                         a.id);
            return 1;
        }
        if (a.asym_patches != b.asym_patches) {
            std::fprintf(stderr,
                         "selftest: model %d asym_patches lost/changed in "
                         "save->load (%zu -> %zu)\n",
                         a.id, a.asym_patches.size(), b.asym_patches.size());
            return 1;
        }
        if (a.mid_band_type != b.mid_band_type) {
            std::fprintf(stderr,
                         "selftest: model %d mid_band_type lost/changed in "
                         "save->load (%d -> %d)\n",
                         a.id, a.mid_band_type, b.mid_band_type);
            return 1;
        }
    }
    std::printf("selftest OK: %zu models, %d with asym_patches, "
                "%d hot middle band, save->load round-trip clean\n",
                original.size(), withPatches, withMidBand);
    return 0;
}

// Phase D probe (2026-10-17 format change): the async layer lives on the ROOM
// now, so the round-trip below covers a LEVEL (rooms incl. asym_patches /
// feature_cells) and proves MigrateAsyncToRooms() moves a legacy model's async
// into the rooms that reference it. Everything is written to a TEMP dir — the
// frozen inputs are never modified.
static int RunLevelAsyncSelftest(const char* modelsPath) {
    namespace fs = std::filesystem;
    const fs::path modelsFile(modelsPath);
    const fs::path roomsDir = modelsFile.parent_path().parent_path();

    std::vector<hero::ModelData> models;
    if (!hero::DataSerializer::LoadModelsFromFile(models, modelsPath)) {
        std::fprintf(stderr, "selftest: cannot load %s\n", modelsPath);
        return 2;
    }
    fs::path levelPath;
    for (const auto& e : fs::directory_iterator(roomsDir)) {
        const std::string n = e.path().filename().string();
        if (n.rfind("level_", 0) == 0 && e.path().extension() == ".json") {
            levelPath = e.path();
            break;
        }
    }
    if (levelPath.empty()) {
        std::fprintf(stderr, "selftest: no level_*.json next to %s\n",
                     modelsPath);
        return 2;
    }

    // --- 1. room-level async round-trip (save -> load) ---------------------
    hero::LevelData level, reloaded;
    if (!hero::DataSerializer::LoadLevelFromFile(level, levelPath.string())) {
        std::fprintf(stderr, "selftest: cannot load %s\n",
                     levelPath.string().c_str());
        return 2;
    }
    const fs::path tmpLevel =
        fs::temp_directory_path() / "savior_editor_selftest_level.json";
    if (!hero::DataSerializer::SaveLevelToFile(level, tmpLevel.string()) ||
        !hero::DataSerializer::LoadLevelFromFile(reloaded, tmpLevel.string())) {
        std::fprintf(stderr, "selftest: level save/reload failed\n");
        return 2;
    }
    fs::remove(tmpLevel);
    if (level.rooms.size() != reloaded.rooms.size()) {
        std::fprintf(stderr, "selftest: room count %zu -> %zu\n",
                     level.rooms.size(), reloaded.rooms.size());
        return 1;
    }
    int roomsWithAsync = 0;
    for (size_t i = 0; i < level.rooms.size(); ++i) {
        const auto& a = level.rooms[i];
        const auto& b = reloaded.rooms[i];
        if (a.asym_patches != b.asym_patches) {
            std::fprintf(stderr,
                         "selftest: room %zu asym_patches lost/changed in "
                         "save->load (%zu -> %zu)\n",
                         i, a.asym_patches.size(), b.asym_patches.size());
            return 1;
        }
        if (a.feature_cells != b.feature_cells) {
            std::fprintf(stderr,
                         "selftest: room %zu feature_cells lost/changed in "
                         "save->load (%zu -> %zu)\n",
                         i, a.feature_cells.size(), b.feature_cells.size());
            return 1;
        }
        if (!a.asym_patches.empty() || !a.feature_cells.empty()) {
            ++roomsWithAsync;
        }
    }

    // --- 2. legacy migration (temp copy, never the frozen stage) -----------
    const fs::path tmpDir = fs::temp_directory_path() / "savior_editor_selftest";
    fs::remove_all(tmpDir);
    fs::create_directories(tmpDir);
    hero::LevelData legacy = level;
    const int legacyId = 90;
    if (legacy.rooms.empty()) {
        std::fprintf(stderr, "selftest: level has no rooms\n");
        return 2;
    }
    legacy.rooms[0].model_id = legacyId;
    legacy.rooms[0].asym_patches.clear();
    legacy.rooms[0].feature_cells.clear();
    if (!hero::DataSerializer::SaveLevelToFile(
            legacy, (tmpDir / "level_001.json").string())) {
        std::fprintf(stderr, "selftest: temp level write failed\n");
        return 2;
    }
    std::vector<hero::ModelData> legacyModels(models);
    hero::ModelData lm;
    lm.id = legacyId;
    lm.name = "legacy async";
    lm.width = 10;
    lm.height = 3;
    lm.tiles.assign(30, 0);
    lm.tiles[1 * 10 + 3] = 10;                  // a PHASE grid tile (legacy)
    lm.asym_patches = {{1, 2, 9}};              // a door patch (legacy)
    legacyModels.push_back(lm);
    const fs::path tmpModels = tmpDir / "models.json";
    if (!hero::DataSerializer::SaveModelsToFile(legacyModels,
                                                tmpModels.string())) {
        std::fprintf(stderr, "selftest: temp models write failed\n");
        return 2;
    }
    if (!hero::DataSerializer::MigrateAsyncToRooms(
            legacyModels, tmpDir.string(), tmpModels.string())) {
        std::fprintf(stderr, "selftest: migration reported no change\n");
        return 1;
    }
    hero::LevelData migrated;
    if (!hero::DataSerializer::LoadLevelFromFile(
            migrated, (tmpDir / "level_001.json").string())) {
        std::fprintf(stderr, "selftest: cannot reload the migrated level\n");
        return 2;
    }
    const auto& mroom = migrated.rooms[0];
    if (mroom.asym_patches.size() != 1 ||
        mroom.asym_patches[0] != std::vector<int>({1, 2, 9})) {
        std::fprintf(stderr, "selftest: migration dropped the door patch\n");
        return 1;
    }
    if (mroom.feature_cells.size() != 1 ||
        mroom.feature_cells[0] != std::vector<int>({1, 3, 10})) {
        std::fprintf(stderr, "selftest: migration dropped the phase cell\n");
        return 1;
    }
    const auto& mmodel = legacyModels.back();
    if (!mmodel.asym_patches.empty() || mmodel.tiles[1 * 10 + 3] != 1) {
        std::fprintf(stderr, "selftest: legacy model async not cleared\n");
        return 1;
    }
    if (hero::DataSerializer::MigrateAsyncToRooms(
            legacyModels, tmpDir.string(), tmpModels.string())) {
        std::fprintf(stderr, "selftest: migration is not idempotent\n");
        return 1;
    }
    fs::remove_all(tmpDir);

    std::printf("selftest: level OK (%zu rooms, %d with room-level async, "
                "legacy migration verified)\n",
                level.rooms.size(), roomsWithAsync);
    return 0;
}

int main(int argc, char* argv[]) {
    if (argc == 3 && std::string(argv[1]) == "--selftest") {
        const int rc = RunSelfTest(argv[2]);
        if (rc != 0) {
            return rc;
        }
        return RunLevelAsyncSelftest(argv[2]);
    }
    QApplication app(argc, argv);
    app.setApplicationName("Savior AI Level Editor");
    app.setOrganizationName("SaviorAI");

    editor::MainWindow window;
    window.show();

    return app.exec();
}
