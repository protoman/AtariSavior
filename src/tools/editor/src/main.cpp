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
#include <algorithm>
#include <cereal/archives/json.hpp>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include "DataSerializer.hpp"
#include "LevelData.hpp"
#include "MainWindow.hpp"
#include "MapCanvas.hpp"

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

// Headless brush test (2026-10-18): the async brushes write the ROOM's async
// layer, which no other test covers. Builds a synthetic stage in code (a model
// shape + one room), drives MapCanvas::ApplyBrushAt directly and asserts the
// room changed — no dialogs may open, so only VALID targets are used (an
// invalid one pops a modal warning that would hang a headless run).
static int RunBrushTest() {
    using editor::MapCanvas;
    using editor::BrushTool;
    hero::LevelData level;
    level.name = "brushtest";
    hero::ModelData model;
    model.id = 0;
    model.name = "brush shape";
    model.width = 10;
    model.height = 3;
    model.tiles.assign(30, (int)hero::TileType::AIR);
    for (int x = 0; x < 10; ++x) {
        model.tiles[0 * 10 + x] = (int)hero::TileType::SOLID_WALL;
        if (x != 9) model.tiles[2 * 10 + x] = (int)hero::TileType::SOLID_WALL;
    }
    model.tiles[1 * 10 + 0] = (int)hero::TileType::AIR;
    model.tiles[1 * 10 + 9] = (int)hero::TileType::AIR;   // right-door mirror
    std::vector<hero::ModelData> models{model};
    // TWO rooms: painting a door and a phase wall in the SAME room is rejected
    // by the alone-per-room rule with a modal warning, which would hang a
    // headless run — so each brush gets its own room.
    for (int i = 0; i < 2; ++i) {
        hero::RoomData r;
        r.room_id = i;
        r.model_id = 0;
        r.room_y = i;
        level.rooms.push_back(r);
    }

    MapCanvas canvas;
    canvas.SetLevelData(&level, &models, 0);
    canvas.SetModels(&models);
    canvas.SetEditMode(false);                 // LEVEL tab: async is room-level

    // door strip on the RIGHT half, col 0 (entityX 20 -> rightHalf, col 0)
    canvas.SetCurrentBrush(BrushTool::DOOR_TILE);
    canvas.ApplyBrushAt(9, 20, 4);             // tileY 4 = model row 1
    if (level.rooms[0].asym_patches.size() != 1 ||
        level.rooms[0].asym_patches[0] != std::vector<int>({1, 0, 9})) {
        std::fprintf(stderr, "brushtest: door brush did not write the ROOM "
                     "(asym_patches=%zu)\n",
                     level.rooms[0].asym_patches.size());
        return 1;
    }

    // phase wall cell on row 1 (room 1: a door + a phase wall in one room is
    // refused by design)
    canvas.SetActiveRoom(1);
    canvas.SetCurrentBrush(BrushTool::PHASE_TILE);
    canvas.ApplyBrushAt(3, 3, 4);
    if (level.rooms[1].feature_cells.size() != 1 ||
        level.rooms[1].feature_cells[0] != std::vector<int>({1, 3, 10})) {
        std::fprintf(stderr, "brushtest: phase brush did not write the ROOM "
                     "(feature_cells=%zu)\n",
                     level.rooms[1].feature_cells.size());
        return 1;
    }

    // Regression (2026-10-18): an older paint wrote one feature cell PER COLUMN.
    // One ERASE click must clear the whole ROW — the per-cell match removed 1 of
    // 10 and the row still resolved, so "delete did nothing" for the user.
    level.rooms[1].feature_cells.clear();
    for (int c = 0; c < 10; ++c)
        level.rooms[1].feature_cells.push_back({1, c, 12});   // HCRUNCH row
    canvas.SetCurrentBrush(BrushTool::ERASE_AIR);
    canvas.ApplyBrushAt(5, 10, 4);        // row 1 (tileY 4), column 5
    if (!level.rooms[1].feature_cells.empty()) {
        std::fprintf(stderr, "brushtest: DELETE left %zu feature cells "
                     "(the Level-tab Delete tool must clear the row)\n",
                     level.rooms[1].feature_cells.size());
        return 1;
    }
    // ... and the same through the Level tab's DELETE tool, which is what a
    // user actually clicks (it used to only erase entities: 2026-10-18).
    for (int c = 0; c < 10; ++c)
        level.rooms[1].feature_cells.push_back({1, c, 12});
    canvas.SetCurrentBrush(BrushTool::DELETE_ENTITY);
    canvas.ApplyBrushAt(5, 10, 4);
    if (!level.rooms[1].feature_cells.empty()) {
        std::fprintf(stderr, "brushtest: DELETE left %zu feature cells "
                     "(the Level-tab Delete tool must clear the row)\n",
                     level.rooms[1].feature_cells.size());
        return 1;
    }

    // erase clears the room's async again (both layers)
    canvas.SetCurrentBrush(BrushTool::ERASE_AIR);
    canvas.ApplyBrushAt(3, 3, 4);              // room 1: the phase cell
    canvas.SetActiveRoom(0);
    canvas.ApplyBrushAt(9, 20, 4);             // room 0: the door strip
    if (!level.rooms[1].feature_cells.empty() ||
        !level.rooms[0].asym_patches.empty()) {
        std::fprintf(stderr, "brushtest: ERASE_AIR left async behind "
                     "(features=%zu patches=%zu)\n",
                     level.rooms[1].feature_cells.size(),
                     level.rooms[0].asym_patches.size());
        return 1;
    }

    // the MODEL must never be touched by an async brush
    if (!model.asym_patches.empty() ||
        std::any_of(model.tiles.begin(), model.tiles.end(), [](int t) {
            return t == (int)hero::TileType::PHASE ||
                   t == (int)hero::TileType::HCRUNCH;
        })) {
        std::fprintf(stderr, "brushtest: async brush wrote the MODEL "
                     "(legacy fields must stay empty)\n");
        return 1;
    }
    std::printf("brushtest: OK (door + phase brushes write the room, ERASE "
                "clears both layers, the model stays clean)\n");
    return 0;
}

// Unified stage file selftest (E1 2026-10-20): save the frozen project's
// models + every level as ONE stage file, reload it and prove (a) the bytes
// are stable across a save->load->save round trip and (b) each reloaded level
// serializes byte-identically to its legacy per-level source (semantic and
// field preservation, including room-level async). Also proves the bare
// `{"models": ..., "levels": ...}` form loads. Everything is TEMP only.
static int RunStageSelftest(const char* roomsDirPath) {
    namespace fs = std::filesystem;
    const fs::path roomsDir(roomsDirPath);
    const fs::path modelsPath = roomsDir / "models" / "models.json";

    std::vector<hero::ModelData> models;
    if (!hero::DataSerializer::LoadModelsFromFile(models, modelsPath.string())) {
        std::fprintf(stderr, "stageselftest: cannot load %s\n",
                     modelsPath.string().c_str());
        return 2;
    }
    std::vector<fs::path> levelFiles;
    for (const auto& e : fs::directory_iterator(roomsDir)) {
        const std::string n = e.path().filename().string();
        if (n.rfind("level_", 0) == 0 && e.path().extension() == ".json") {
            levelFiles.push_back(e.path());
        }
    }
    std::sort(levelFiles.begin(), levelFiles.end());
    if (levelFiles.empty()) {
        std::fprintf(stderr, "stageselftest: no level_*.json in %s\n",
                     roomsDir.string().c_str());
        return 2;
    }

    std::vector<hero::LevelData> levels;
    for (const auto& path : levelFiles) {
        hero::LevelData level;
        if (!hero::DataSerializer::LoadLevelFromFile(level, path.string())) {
            std::fprintf(stderr, "stageselftest: cannot load %s\n",
                         path.string().c_str());
            return 2;
        }
        levels.push_back(level);
    }

    const fs::path tmp1 =
        fs::temp_directory_path() / "savior_stage_selftest_1.json";
    const fs::path tmp2 =
        fs::temp_directory_path() / "savior_stage_selftest_2.json";
    const fs::path bare =
        fs::temp_directory_path() / "savior_stage_selftest_bare.json";
    if (!hero::DataSerializer::SaveStageToFile(levels, models, tmp1.string())) {
        std::fprintf(stderr, "stageselftest: save failed\n");
        return 2;
    }

    std::vector<hero::LevelData> levels2;
    std::vector<hero::ModelData> models2;
    if (!hero::DataSerializer::LoadStageFromFile(levels2, models2,
                                                 tmp1.string())) {
        std::fprintf(stderr, "stageselftest: reload failed\n");
        fs::remove(tmp1);
        return 2;
    }
    if (levels2.size() != levels.size() || models2.size() != models.size()) {
        std::fprintf(stderr, "stageselftest: counts changed "
                     "(%zu/%zu levels, %zu/%zu models)\n",
                     levels.size(), levels2.size(),
                     models.size(), models2.size());
        fs::remove(tmp1);
        return 1;
    }
    if (!hero::DataSerializer::SaveStageToFile(levels2, models2, tmp2.string())) {
        std::fprintf(stderr, "stageselftest: second save failed\n");
        fs::remove(tmp1);
        return 2;
    }

    auto readAll = [](const fs::path& p) {
        std::ifstream in(p, std::ios::binary);
        return std::string((std::istreambuf_iterator<char>(in)),
                           std::istreambuf_iterator<char>());
    };
    const std::string first = readAll(tmp1);
    const bool byteStable = first == readAll(tmp2);
    fs::remove(tmp2);

    // Each reloaded stage level must serialize identically to its legacy file.
    const fs::path tmpLevel =
        fs::temp_directory_path() / "savior_stage_selftest_level.json";
    for (size_t i = 0; i < levels.size(); ++i) {
        if (!hero::DataSerializer::SaveLevelToFile(levels[i],
                                                   tmpLevel.string())) {
            std::fprintf(stderr, "stageselftest: level %zu save failed\n", i);
            return 2;
        }
        const std::string legacyBytes = readAll(tmpLevel);
        if (!hero::DataSerializer::SaveLevelToFile(levels2[i],
                                                   tmpLevel.string())) {
            std::fprintf(stderr, "stageselftest: level %zu save failed\n", i);
            return 2;
        }
        if (legacyBytes != readAll(tmpLevel)) {
            std::fprintf(stderr,
                         "stageselftest: stage level %zu differs from the "
                         "legacy level after save->load\n", i);
            return 1;
        }
    }
    fs::remove(tmpLevel);

    // Bare form (no `stage` wrapper) must load too.
    bool bareOk = false;
    {
        std::ofstream os(bare.string());
        if (os.is_open()) {
            hero::StageFile sf;
            sf.models = models;
            sf.levels = levels;
            cereal::JSONOutputArchive archive(os);
            archive(sf);
        }
        std::vector<hero::LevelData> bareLevels;
        std::vector<hero::ModelData> bareModels;
        bareOk = hero::DataSerializer::LoadStageFromFile(
                     bareLevels, bareModels, bare.string()) &&
                 bareLevels.size() == levels.size();
        fs::remove(bare);
    }

    if (!byteStable) {
        std::fprintf(stderr, "stageselftest: save->load->save is not "
                     "byte-identical\n");
        return 1;
    }
    if (!bareOk) {
        std::fprintf(stderr, "stageselftest: bare {models, levels} form "
                     "does not load\n");
        return 1;
    }
    std::printf("stageselftest: OK (%zu levels, %zu models, byte-stable, "
                "bare form accepted)\n",
                levels.size(), models.size());
    return 0;
}

int main(int argc, char* argv[]) {
    if (argc == 2 && std::string(argv[1]) == "--brushtest") {
        QApplication app(argc, argv);
        return RunBrushTest();
    }
    if (argc == 3 && std::string(argv[1]) == "--selftest") {
        const int rc = RunSelfTest(argv[2]);
        if (rc != 0) {
            return rc;
        }
        const int rc2 = RunLevelAsyncSelftest(argv[2]);
        if (rc2 != 0) {
            return rc2;
        }
        // models.json lives in <rooms>/models/ -> the frozen levels are next
        // to that folder.
        const std::filesystem::path roomsDir =
            std::filesystem::path(argv[2]).parent_path().parent_path();
        return RunStageSelftest(roomsDir.string().c_str());
    }
    QApplication app(argc, argv);
    app.setApplicationName("Savior AI Level Editor");
    app.setOrganizationName("SaviorAI");

    editor::MainWindow window;
    window.show();

    return app.exec();
}
