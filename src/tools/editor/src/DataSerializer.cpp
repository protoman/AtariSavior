/*
 * Savior AI - Atari 2600 (de)Remake of HERO
 * Copyright (C) 2026 Savior SDL Team
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

#include "DataSerializer.hpp"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <filesystem>
#include <map>
#include <optional>
#include <queue>
#include <tuple>
#include <set>
#include <vector>
#include <sstream>
#include <iterator>
#include <stdexcept>
#include <string>

namespace hero {

// ---------------------------------------------------------------------------
// Async walls moved from MODEL to ROOM (2026-10-17). Mirrors
// tools/migrate_async_to_rooms.py so the editor and the CLI agree.
// ---------------------------------------------------------------------------
namespace {
constexpr int kPhaseTile = 10;
constexpr int kVcrunchTile = 11;
constexpr int kHcrunchTile = 12;
constexpr int kSolidWall = 1;
// kRoomWidth lives in LevelData.hpp (shared with the exit-span constants).

bool IsFeatureTile(int t) {
    return t == kPhaseTile || t == kVcrunchTile || t == kHcrunchTile;
}

// model id -> {patches, feature cells} harvested from the legacy fields.
struct LegacyAsync {
    std::vector<std::vector<int>> patches;
    std::vector<std::vector<int>> features;
};
}  // namespace

bool DataSerializer::MigrateAsyncToRooms(std::vector<ModelData>& models,
                                         const std::string& levelsDir,
                                         const std::string& modelsPath) {
    namespace fs = std::filesystem;
    std::map<int, LegacyAsync> legacy;
    for (const auto& m : models) {
        LegacyAsync a;
        a.patches = m.asym_patches;
        const int w = m.width > 0 ? m.width : kRoomWidth;
        for (size_t i = 0; i < m.tiles.size(); ++i) {
            if (IsFeatureTile(m.tiles[i])) {
                a.features.push_back({static_cast<int>(i) / w,
                                      static_cast<int>(i) % w, m.tiles[i]});
            }
        }
        if (!a.patches.empty() || !a.features.empty()) {
            legacy[m.id] = a;
        }
    }
    if (legacy.empty()) {
        return false;                       // already migrated (or no async)
    }

    bool changed = false;
    std::error_code ec;
    std::vector<fs::path> levels;
    if (fs::is_directory(levelsDir, ec)) {
        for (const auto& e : fs::directory_iterator(levelsDir, ec)) {
            const std::string name = e.path().filename().string();
            if (name.rfind("level_", 0) == 0 && e.path().extension() == ".json") {
                levels.push_back(e.path());
            }
        }
    }
    std::sort(levels.begin(), levels.end());
    for (const auto& path : levels) {
        LevelData level;
        if (!LoadLevelFromFile(level, path.string())) {
            std::cerr << "migrate: cannot load " << path << std::endl;
            continue;
        }
        bool touched = false;
        for (auto& room : level.rooms) {
            const auto it = legacy.find(room.model_id);
            if (it == legacy.end()) {
                continue;
            }
            if (!it->second.patches.empty() && room.asym_patches.empty()) {
                room.asym_patches = it->second.patches;
                touched = true;
            }
            if (!it->second.features.empty() && room.feature_cells.empty()) {
                room.feature_cells = it->second.features;
                touched = true;
            }
        }
        if (touched && SaveLevelToFile(level, path.string())) {
            std::cout << "migrate: " << path.filename()
                      << " async walls moved to rooms" << std::endl;
            changed = true;
        }
    }

    for (auto& m : models) {
        if (!m.asym_patches.empty()) {
            m.asym_patches.clear();
            changed = true;
        }
        const int w = m.width > 0 ? m.width : kRoomWidth;
        for (size_t i = 0; i < m.tiles.size(); ++i) {
            if (IsFeatureTile(m.tiles[i])) {
                m.tiles[i] = kSolidWall;    // same PF byte (feature = solid)
                changed = true;
            }
        }
    }
    if (changed && !modelsPath.empty()) {
        SaveModelsToFile(models, modelsPath);   // persist the cleared models
    }
    return changed;
}

bool DataSerializer::SaveLevelToFile(const LevelData& level, const std::string& filepath) {
    try {
        std::ofstream os(filepath);
        if (!os.is_open()) return false;
        cereal::JSONOutputArchive archive(os);
        archive(cereal::make_nvp("level", level));
        return true;
    } catch (const std::exception& e) {
        std::cerr << "Failed to save level to " << filepath << ": " << e.what() << std::endl;
        return false;
    }
}

bool DataSerializer::LoadLevelFromFile(LevelData& level, const std::string& filepath) {
    try {
        std::ifstream is(filepath);
        if (!is.is_open()) return false;
        std::string json((std::istreambuf_iterator<char>(is)), std::istreambuf_iterator<char>());
        if (json.find("\"cereal_class_version\"") == std::string::npos) {
            const size_t levelName = json.find("\"level\"");
            const size_t objectStart = levelName == std::string::npos
                                           ? std::string::npos
                                           : json.find('{', levelName);
            if (objectStart != std::string::npos) {
                const auto version = json.find("\"miner_dir\"") == std::string::npos ? 0 : 1;
                json.insert(objectStart + 1,
                            "\n        \"cereal_class_version\": " +
                                std::to_string(version) + ",");
            }
        }
        std::istringstream input(json);
        cereal::JSONInputArchive archive(input);
        archive(cereal::make_nvp("level", level));
        return true;
    } catch (const std::exception& e) {
        std::cerr << "Failed to load level from " << filepath << ": " << e.what() << std::endl;
        return false;
    }
}

bool DataSerializer::SaveModelsToFile(const std::vector<ModelData>& models, const std::string& filepath) {
    try {
        std::ofstream os(filepath);
        if (!os.is_open()) return false;
        cereal::JSONOutputArchive archive(os);
        ModelsFile mf;
        mf.models = models;
        archive(cereal::make_nvp("models_file", mf));
        return true;
    } catch (const std::exception& e) {
        std::cerr << "Failed to save models to " << filepath << ": " << e.what() << std::endl;
        return false;
    }
}

bool DataSerializer::LoadModelsFromFile(std::vector<ModelData>& models, const std::string& filepath) {
    try {
        std::ifstream is(filepath);
        if (!is.is_open()) return false;
        cereal::JSONInputArchive archive(is);
        ModelsFile mf;
        archive(cereal::make_nvp("models_file", mf));
        models = mf.models;
        MigrateToFourBands(models, nullptr);   // N=4: 3-row files open 4-band
        return true;
    } catch (const std::exception& e) {
        std::cerr << "Failed to load models from " << filepath << ": " << e.what() << std::endl;
        return false;
    }
}

// ---------------------------------------------------------------------------
// Unified stage file (E1 2026-10-20): models + every level in ONE json.
// ---------------------------------------------------------------------------
namespace {
// cereal's class-version mechanism throws when `cereal_class_version` is
// absent, so a hand-written or generator-emitted stage file would lose the
// optional level fields (miner_dir). Inject the key into every level object
// (elements of the top-level `levels` array) when the file has none.
std::string VersionStageLevels(const std::string& json) {
    if (json.find("\"cereal_class_version\"") != std::string::npos) {
        return json;
    }
    const size_t key = json.find("\"levels\"");
    if (key == std::string::npos) return json;
    const size_t start = json.find('[', key);
    if (start == std::string::npos) return json;

    std::vector<size_t> inserts;   // positions right after each level's '{'
    int depth = 0;
    bool inString = false;
    bool escape = false;
    for (size_t i = start + 1; i < json.size(); ++i) {
        const char c = json[i];
        if (inString) {
            if (escape) {
                escape = false;
            } else if (c == '\\') {
                escape = true;
            } else if (c == '"') {
                inString = false;
            }
            continue;
        }
        if (c == '"') {
            inString = true;
        } else if (c == '{') {
            if (depth == 0) inserts.push_back(i + 1);
            ++depth;
        } else if (c == '}') {
            --depth;
        } else if (c == ']' && depth == 0) {
            break;
        }
    }
    std::string out = json;
    // Back to front so the earlier offsets stay valid.
    for (auto it = inserts.rbegin(); it != inserts.rend(); ++it) {
        out.insert(*it, "\n\"cereal_class_version\": 1,");
    }
    return out;
}
}  // namespace

bool DataSerializer::SaveStageToFile(const std::vector<LevelData>& levels,
                                     const std::vector<ModelData>& models,
                                     const std::string& filepath) {
    try {
        std::ofstream os(filepath);
        if (!os.is_open()) return false;
        cereal::JSONOutputArchive archive(os);
        StageFile stage;
        stage.models = models;
        stage.levels = levels;
        archive(cereal::make_nvp("stage", stage));
        return true;
    } catch (const std::exception& e) {
        std::cerr << "Failed to save stage to " << filepath << ": "
                  << e.what() << std::endl;
        return false;
    }
}

void DataSerializer::MigrateToFourBands(std::vector<ModelData>& models,
                                        std::vector<LevelData>* levels) {
    // 1. Collect, per model, the single M1 strip column that every room using
    //    it agrees on (-1 = rooms disagree / no strip). The strip is a
    //    WHOLE-CAVE latch (ENAM1), so its column must be wall-or-patched in
    //    EVERY band; the inserted AIR band would expose it.
    std::map<int, int> m1Col;
    std::map<int, int> gained;   // model id -> 1 when a band was inserted
    if (levels) {
        for (const auto& level : *levels) {
            for (const auto& room : level.rooms) {
                std::set<int> cols;
                for (const auto& p : room.asym_patches) {
                    if (p.size() == 4 && p[3] == 1) cols.insert(p[1]);
                }
                // A room with NO strip does not constrain the column: only the
                // rooms that paint one must agree (the extra wall it adds in
                // the new band is verified by the connectivity guard below).
                if (cols.empty()) continue;
                const int col = cols.size() == 1 ? *cols.begin() : -1;
                auto it = m1Col.find(room.model_id);
                if (it == m1Col.end()) m1Col[room.model_id] = col;
                else if (it->second != col) it->second = -1;
            }
        }
    }

    // 2. Pad every 3-row model to [row0, row1, AIR, row2].
    for (auto& m : models) {
        const int w = m.width > 0 ? m.width : kRoomWidth;
        if (m.height != 3 || (int)m.tiles.size() != w * 3) continue;
        std::vector<int> next(m.tiles.begin(), m.tiles.begin() + 2 * w);
        next.insert(next.end(), w, (int)TileType::AIR);
        next.insert(next.end(), m.tiles.begin() + 2 * w, m.tiles.end());
        m.tiles = std::move(next);
        m.height = 4;
        gained[m.id] = 1;
    }
    if (!levels || gained.empty()) return;

    // 3. Hide the strip in the inserted band when the authored model already
    //    has that column SOLID in every band the strip does not cross (the
    //    generator's side-gate door). Repeating the wall cannot seal a
    //    corridor: the column is solid above and below the door band already.
    //    A ladder-style strip (open above/below, e.g. the live stage's L1R2)
    //    is left alone — that is a per-room authoring call (patch or wall).
    for (auto& m : models) {
        auto it = m1Col.find(m.id);
        if (it == m1Col.end() || it->second < 0 || !gained.count(m.id)) {
            continue;
        }
        const int w = m.width > 0 ? m.width : kRoomWidth;
        const int col = it->second;
        if (col >= w || (int)m.tiles.size() != w * 4) continue;
        bool solidAround = true;
        for (int band : {0, 3}) {
            const int t = m.tiles[band * w + col];
            if (t == (int)TileType::AIR) { solidAround = false; break; }
        }
        if (solidAround) m.tiles[2 * w + col] = (int)TileType::SOLID_WALL;
    }

    // 4. Authored rows ride the model: the old bottom row is band 3 now.
    for (auto& level : *levels) {
        for (auto& room : level.rooms) {
            if (!gained.count(room.model_id)) continue;
            for (auto& p : room.asym_patches) {
                if (!p.empty() && p[0] == 2) p[0] = 3;
            }
            for (auto& f : room.feature_cells) {
                if (!f.empty() && f[0] == 2) f[0] = 3;
            }
        }
    }

    // 5. Anything the auto-hide could not decide is the author's call.
    for (auto& level : *levels) {
        for (auto& room : level.rooms) {
            if (!gained.count(room.model_id)) continue;
            auto it = m1Col.find(room.model_id);
            const bool hidden = it != m1Col.end() && it->second >= 0;
            if (!hidden) {
                for (const auto& p : room.asym_patches) {
                    if (p.size() == 4 && p[3] == 1) {
                        std::cerr << "migrate: model " << room.model_id
                                  << " (room " << room.room_id << "): the "
                                     "M1 strip is drawn in EVERY band, so "
                                     "band 2 col " << p[1] << " must be "
                                     "WALL or carry an M1 patch (otherwise "
                                     "a 1 px line shows in the new air "
                                     "band)" << std::endl;
                    }
                }
            }
        }
    }
}

bool DataSerializer::LoadStageFromFile(std::vector<LevelData>& levels,
                                       std::vector<ModelData>& models,
                                       const std::string& filepath) {
    std::string json;
    try {
        std::ifstream is(filepath);
        if (!is.is_open()) return false;
        json.assign((std::istreambuf_iterator<char>(is)),
                    std::istreambuf_iterator<char>());
    } catch (const std::exception& e) {
        std::cerr << "Failed to read stage " << filepath << ": " << e.what()
                  << std::endl;
        return false;
    }
    const std::string versioned = VersionStageLevels(json);
    // Canonical form first ({"stage": {...}}), then the bare form.
    try {
        std::istringstream input(versioned);
        cereal::JSONInputArchive archive(input);
        StageFile stage;
        archive(cereal::make_nvp("stage", stage));
        levels = stage.levels;
        models = stage.models;
        MigrateToFourBands(models, &levels);
        return true;
    } catch (const cereal::Exception&) {
        // fall through to the bare form
    } catch (const std::exception&) {
        // fall through too — the bare attempt reports the real error
    }
    try {
        std::istringstream input(versioned);
        cereal::JSONInputArchive archive(input);
        StageFile stage;
        archive(stage);
        levels = stage.levels;
        models = stage.models;
        MigrateToFourBands(models, &levels);
        return true;
    } catch (const std::exception& e) {
        std::cerr << "Failed to load stage from " << filepath << ": "
                  << e.what() << std::endl;
        return false;
    }
}

// Atari 2600-inspired cave palettes per level (RGB), shared by generators
static const int kLevelPalettes[20][3] = {
    {180, 80, 0},    // L1: Red/Orange
    {0, 140, 180},   // L2: Cyan/Blue
    {40, 160, 40},   // L3: Green
    {180, 140, 0},   // L4: Yellow/Gold
    {160, 40, 160},  // L5: Purple
    {180, 60, 60},   // L6: Crimson
    {40, 180, 160},  // L7: Teal
    {140, 100, 40},  // L8: Ochre
    {60, 60, 180},   // L9: Deep Blue
    {180, 100, 140}, // L10: Pink/Rose
    {100, 140, 60},  // L11: Lime Green
    {200, 120, 40},  // L12: Amber
    {80, 160, 200},  // L13: Sky Blue
    {160, 80, 160},  // L14: Violet
    {180, 180, 60},  // L15: Olive
    {200, 60, 100},  // L16: Magenta
    {60, 180, 80},   // L17: Emerald
    {140, 80, 200},  // L18: Purple Blue
    {200, 140, 80},  // L19: Copper
    {220, 220, 220}  // L20: Silver Gray
};

// ---------------------------------------------------------------------------
// E2 (2026-10-20): the 20-LEVEL STAGE GENERATOR.
//
// Goal: level n has n rooms (1..20 = 210 rooms) at a ROM cost the C7 level-data
// split can hold. The cost lever is SHARED MODEL SHAPES: the converter emits
// one shape block per REFERENCED model id, so 210 rooms must resolve to a
// handful of shapes instead of one model per room (the retired
// GenerateAll20DefaultLevels built a fresh 60-tile model per room).
//
// SHAPE LIBRARY — keyed by the CARVED exits, three bits only:
//   SHAPE_N / SHAPE_S  room above / below  (every vertical pair is a corridor)
//   SHAPE_H            the mirrored horizontal opening (west AND east) is cut
// West and east share ONE bit on purpose: the playfield is REFLECTED, so cell 0
// (the room's outer edge) is drawn on both sides of the room and collision
// mirrors too (PlayerHitsMap maps display col >= 20 to 39-col). There is no
// way to cut only one side — and two models differing only in "which side"
// would be byte-identical anyway (the converter still counts them separately).
//
// LAYOUT — a 2-column serpentine, mirror-safe:
//   level n <= 10 : x=0, y=0..n-1                   (pure vertical corridor)
//   level n >  10 : x=0, y=0..9, the turn, then x=1, y=9 -> 10-m going UP
// Exits are DERIVED FROM ADJACENCY at run time (C1: bank2 ExitScanB2 scans the
// stored position column), so the carve MUST agree with the neighbour set:
//   * every vertically adjacent pair is carved on BOTH sides;
//   * horizontally, both columns are occupied on many rows, so every such pair
//     is WALLED (solid col 0 / row 1 in both models): the ROM still sees the
//     adjacency, but the player can never reach the edge to use it;
//   * the ONE carved horizontal pair is the turn, and both of its rooms carry
//     SHAPE_H — a one-sided carve would drop the player inside the neighbour's
//     wall (EnterRoom places him at x=4 = that room's col 0).
// The turn rooms also show a dead aperture on their far side (nobody there):
// the exit scan finds no room (bank2 ExitNoneB2) and the player stops at the
// edge. That is the only layout artefact, and it cannot tear a transition.
//
// Deterministic BY CONSTRUCTION: no RNG, no clock, no unordered container; the
// model ids are the ascending shape keys and rooms are emitted in walk order,
// so two runs are byte-identical (tools/test_generator.py asserts it).
// ---------------------------------------------------------------------------
namespace {

constexpr int kStageLevels = 20;     // level n = 1..20
constexpr int kGridW = 5;            // layout lattice (positions are 4-bit)
constexpr int kGridH = 5;
// Exit bits + hazard bits (2026-10-20: the generated stage got its HERO-style
// variety — hot bands, a keyed gate, water goals with raft/tentacle).
enum ShapeBits {
    SHAPE_N = 1,
    SHAPE_S = 2,
    SHAPE_H = 4,
    SHAPE_START = 8,
    SHAPE_HOT = 16,      // row-1 walls hot (model mid_band_type = 1)
    SHAPE_GATE = 32,     // row-1 wall with ONE open gap (door / gate column)
    SHAPE_WATER = 64,    // row-2 open water (bottom band, raft/tentacle)
    SHAPE_2GAP = 128,    // TWO vertical gaps (cells 3 and 6) instead of the
                         // centre 8-9: the next room must repeat the pair
    SHAPE_CHANNEL = 256, // HERO-style water crossing: hot row-1 ceiling
                         // (cells 1..7), low channel over the water, raft
    // User rule 2026-10-21: no room may be a straight vertical fall. From
    // level 6 every LINK is NARROW (one corridor cell) or WIDE (both), and
    // consecutive links alternate, so each through-room has a different number
    // of exits at the top and the bottom and the player has to line up.
    SHAPE_N1 = 1 << 13,  // narrow TOP opening (cell vA only)
    SHAPE_S1 = 1 << 14,  // narrow BOTTOM opening
    // User rule 2026-10-25: a hcrunch room needs a gap of >= 2 tiles above
    // AND under (a one-tile hole cannot be lined up before the crush). These
    // widen the ceiling / floor to the four cells 3..6 when the link flavor
    // only offers single cells (two-gap or narrow links); the room below a
    // widened floor widens its ceiling too (upper floor must stay inside the
    // lower ceiling).
    SHAPE_WN = 1 << 15,
    SHAPE_WS = 1 << 16
};
constexpr int kGateCol = 4;          // the gate/door cell in row 1
constexpr int kPhaseCell = 2;       // phase wall: solid above AND below
constexpr int kGapA = 3;             // 2-gap columns (model cells)
constexpr int kGapB = 6;
// Archetype interior (HERO-like variety for ordinary/hot rooms): 3 bits in
// the mask, applied AFTER the exits/hazards. Ids 1..5 = normal families,
// 6..8 = hot families. Only cells 1..7 are ever touched (0 = H exit, 8/9 =
// the vertical shaft), and the 2-gap cells are re-opened afterwards.
constexpr int kArchShift = 9;
constexpr int kArchMask = 15;   // 4 bits: hot archetypes use ids 8..14
// Shape budget: extra archetype variants are enabled ONLY while the library
// fits. The base schedule is 40 shapes (the current bank3 slot); after the
// two-slot split raises the shape slot, bump this (tools/bank3_data_sizes.py
// reports the headroom). With the budget at the current count the generator
// output is byte-identical to the pre-budget build.
// Shape budget = the 7-bit index cap (128, LAYOUT 8 2026-10-24: the shape
// index is b6-0 and the band flag moved to b7, so the old 6-bit/64 ceiling is
// gone). The maze layout multiplies the exit signatures (N/S/H x 2Gap x
// narrow-gap), so the archetype count is the knob that is spent first
// (Build20LevelStage picks the widest set that fits) — and the REAL limit is
// the bank3 shapes window (emit_spills hard-fails, test_generator gates a 64 B
// slack floor), not the index.
constexpr int kShapeBudget = 128;
// Shape-window guard for the widened hcrunch rooms (bank3 shapes slack floor).
constexpr int kCrunchShapeCap = 95;
const char* const kArch[8][3] = {
    {"..........", "..........", ".........."},          // 0 shaft
    {"..###.....", "..........", ".....###.."},          // 1 ledge ladder
    {"..........", "...#.#....", ".........."},          // 2 pillars
    {"...#......", "....#.....", ".........."},          // 3 steps
    {"......#...", "......##..", ".........."},          // 4 side pocket
    {"..##......", ".....#....", "......##.."},          // 5 zigzag
    // extra families (shape-budget mode only)
    {".#.#......", "..#..#....", "......#.#."},          // 6 spiral
    {"..#.......", "..#..#....", ".......#.."},          // 7 gallery
};
// Hot archetypes must SHAPE THE PATH (user 2026-10-21): every one blocks the
// centre (cells 8/9 = the vertical shaft) and forces a detour through an
// offset gap. Ids 8..14.
const char* const kArchHot[7] = {
    "#####.####",   // 8  gate: one gap at cell 5 (the shaft is hot)
    "###.##.###",   // 9  split: gaps at 3 and 6 (choose)
    "#.#.#.#.##",   // 10 comb: weave through 1/3/5/7
    "##.#######",   // 11 align (>level 10): single offset gap at cell 2
    "##.####.##",   // 12 twin gaps at 2 and 7 (budget)
    "#.####.###",   // 13 stairs: gaps at 1 and 6 (budget)
    "####.#####",   // 14 HOT START: the drop column (cell 4) stays open,
                    //    else the spawn lands on a hot wall (budget mode)
};
const int kArchHotGapX[7] = {10, 6, 10, 4, 4, 2, 8};   // cell*2
// The miner must STAND on a solid block (user rule 2026-10-21: a person to
// rescue does not swim/fly). miner_x is in CELL units: the converter turns it
// into display col `miner_x * 2` (8 px per cell), so cell 4 = px 32 and the
// mirrored cell (editor x 15) = px 120. The water-goal rock sits on cell 4 in
// the half-model, which the reflected playfield also draws on the right.
const int kMinerCell = 4;
const float kMinerX = (float)kMinerCell;      // display col 8  (px 32)
const float kMinerFarX = 15.0f;               // display col 30 (px 120)
const char* const kArchName[15] = {
    "", "Ladder", "Pillars", "Steps", "Pocket", "Zigzag", "Spiral",
    "Gallery", "HotGate", "HotSplit", "HotComb", "HotAlign", "HotTwin",
    "HotStair", "HotDrop"};
// Base choices vs budget-enabled choices (ids).
const int kNormalBase[5] = {1, 2, 3, 4, 5};
const int kNormalExtra[7] = {1, 2, 3, 4, 5, 6, 7};
const int kHotBase[3] = {8, 9, 10};
const int kHotLate[4] = {8, 9, 10, 11};
const int kHotExtra[6] = {8, 9, 10, 11, 12, 13};

// Grid cell of a room in the level (x = column, y = row; rooms at the same y
// in different columns are horizontally adjacent and therefore "connected"
// as far as the ROM is concerned).
struct GridPos {
    int x = 0;
    int y = 0;
};
bool HasRoomAt(const std::vector<GridPos>& walk, int x, int y);

// The CHANNEL room (water crossing from level 11): a hot row-1 ceiling forces
// the player down to the low channel, where the raft crosses the water to the
// side exit (HERO-like). It needs a room that runs LEFT-RIGHT (a side
// neighbour on each side), and it must not be the goal (the miner would stand
// in the water). With the maze layout the room is chosen by distance to the
// goal: the LAST room with both side neighbours.
// Rooms the finishability repair demoted from channel to a plain room: set by
// Build20LevelStage's outer loop (level, x, y), null outside a build.
const std::set<std::tuple<int, int, int>>* g_channelOff = nullptr;

bool IsChannelRoom(int level, const std::vector<GridPos>& walk,
                   const GridPos& pos) {
    if (level < 11 || walk.size() < 3) return false;
    if (g_channelOff && g_channelOff->count({level, pos.x, pos.y})) return false;
    const GridPos& goal = walk.back();
    if (pos.x == goal.x && pos.y == goal.y) return false;
    // User rule 2026-10-29: a water room has no exit or entry at its bottom (the
    // player flying up out of a room below arrives in the water and drowns).
    if (!HasRoomAt(walk, pos.x - 1, pos.y)
            || !HasRoomAt(walk, pos.x + 1, pos.y)
            || HasRoomAt(walk, pos.x, pos.y + 1)) {
        return false;
    }
    // Nearest to the goal wins (deterministic: the first in row-major order).
    const int want = std::abs(pos.x - goal.x) + std::abs(pos.y - goal.y);
    for (const GridPos& other : walk) {
        if (&other == &pos) continue;
        if (other.x == goal.x && other.y == goal.y) continue;
        if (g_channelOff && g_channelOff->count({level, other.x, other.y}))
            continue;                       // demoted by the reach repair
        if (!HasRoomAt(walk, other.x - 1, other.y)
                || !HasRoomAt(walk, other.x + 1, other.y)
                || HasRoomAt(walk, other.x, other.y + 1)) {
            continue;
        }
        const int d = std::abs(other.x - goal.x) + std::abs(other.y - goal.y);
        if (d < want || (d == want
                && (other.y < pos.y || (other.y == pos.y && other.x < pos.x)))) {
            return false;
        }
    }
    return true;
}

std::string ShapeName(int mask) {
    if (mask == 0) {
        return "Sealed";
    }
    std::string name;
    auto add = [&name](const char* part) {
        name += name.empty() ? part : std::string("+") + part;
    };
    if (mask & SHAPE_N) add((mask & SHAPE_N1) ? "n" : "N");
    if (mask & SHAPE_S) add((mask & SHAPE_S1) ? "s" : "S");
    if (mask & SHAPE_H) add("H");
    if (mask & SHAPE_START) add("Start");
    if (mask & SHAPE_GATE) add("Gate");
    if (mask & SHAPE_WATER) add("Water");
    if (mask & SHAPE_CHANNEL) add("Channel");
    if (mask & SHAPE_2GAP) add("2Gap");
    if (mask & SHAPE_WN) add("wideTop");
    if (mask & SHAPE_WS) add("wideBottom");
    const int arch = (mask >> kArchShift) & kArchMask;
    if (arch) add(kArchName[arch]);
    return name;
}

// SIZE: the E2 stage generator still speaks THREE bands (its plans, exits and
// QA expectations are built around 3 bands / 3 rows). The editor grid and
// every loaded/saved model are 4 bands (kRoomHeight); a generated 3-row model
// is migrated to [r0, r1, AIR, r2] on load, exactly like any legacy file.
constexpr int kGenRows = 3;

ModelData MakeShapeModel(int modelId, int mask) {
    ModelData model;
    model.id = modelId;
    model.name = "Shape " + ShapeName(mask);
    model.width = kRoomWidth;
    model.height = kGenRows;
    model.tiles.assign(kRoomWidth * kGenRows, (int)TileType::AIR);
    // Border walls: rows 0 and 2 are full bands (a floor/ceiling row), and the
    // middle band's only wall is COL 0 — the mirrored OUTER edge. Col 9 is the
    // centre seam, NOT a boundary: a solid cell there would split the middle
    // band into two chambers and choke the vertical shaft (the live rooms keep
    // it open too: row 1 = "#.........").
    for (int x = 0; x < kRoomWidth; ++x) {
        model.tiles[x] = (int)TileType::SOLID_WALL;                    // row 0
        model.tiles[(kGenRows - 1) * kRoomWidth + x] =
            (int)TileType::SOLID_WALL;                                 // row 2
    }
    for (int y = 0; y < kGenRows; ++y) {
        model.tiles[y * kRoomWidth] = (int)TileType::SOLID_WALL;        // col 0
    }

    if (mask & SHAPE_N) {
        for (int x = kVertExitA; x <= kVertExitB; ++x)
            model.tiles[x] = (int)TileType::AIR;
    }
    if (mask & SHAPE_S) {
        for (int x = kVertExitA; x <= kVertExitB; ++x)
            model.tiles[(kGenRows - 1) * kRoomWidth + x] =
                (int)TileType::AIR;
    }
    if (mask & SHAPE_H) {
        // N=4: open the side in every WALKABLE band (row 1..height-2);
        // a 3-row plan model only has band 1 there.
        for (int y = kHorizExitA;
             y <= std::min(kHorizExitB, kGenRows - 2); ++y)
            model.tiles[y * kRoomWidth + kHorizExitCol] = (int)TileType::AIR;
    }
    if (mask & SHAPE_START) {
        // Level start rooms: the kernel drops the player in at LevelStartX/Y =
        // RoomX 39 (lit span px 32-39), RoomY 24 = display col 8 = CELL 4 of the TOP band, and DropStep
        // bypasses collision — a solid band there would drop him INSIDE a wall.
        // Open cells 2..6 (the drop slot); 7..9 stay solid so an async block
        // can sit at row 1 col 7 (the M1 column must be walled in the other
        // bands, 2026-10-21).
        for (int x = 2; x <= 6; ++x)
            model.tiles[x] = (int)TileType::AIR;
        // He spawns at RoomY 24 (box 24-45), so the drop column must be open in
        // band 1 as well: a wall at cell 4 there killed him on every spawn
        // (level 13, found by tools/playbot.py 2026-10-28).
        model.tiles[1 * kRoomWidth + 4] = (int)TileType::AIR;
    }
    if (mask & SHAPE_HOT) {
        // HERO-style hot band: two symmetric wall blocks narrow the middle
        // band, the shaft keeps cells 1/4/5/8/9. mid_band_type = 1 makes
        // convert promote every row-1 wall to H (solid + lethal touch).
        for (int x : {2, 3, 6, 7}) {
            model.tiles[1 * kRoomWidth + x] = (int)TileType::SOLID_WALL;
        }
        model.mid_band_type = 1;
    }
    if (mask & SHAPE_GATE) {
        // Keyed gate: row 1 is a wall except the room's VERTICAL CORRIDOR,
        // which is where the door patches sit. A gap anywhere else is
        // unreachable — the player descends through the corridor cells, and a
        // door at cell 4 while the exits are 8/9 (or 3/6) soft-locked the
        // level (user report 2026-10-21: level 13 room 4 could not be passed).
        for (int x = 1; x < kRoomWidth; ++x) {
            model.tiles[1 * kRoomWidth + x] = (int)TileType::SOLID_WALL;
        }
        // ONE door cell: the M1 patch strip allows a single column per side,
        // and the door must be the only way down (the other corridor cell
        // stays a wall, a dead-end niche from band 0/2).
        const int doorCell = (mask & SHAPE_2GAP) ? kGapA : kVertExitA;
        model.tiles[1 * kRoomWidth + doorCell] = (int)TileType::AIR;
    }
    if (mask & SHAPE_2GAP) {
        // Two vertical gaps: the pair is repeated in the ceiling and the
        // floor, so a room below inherits BOTH openings. START rooms keep
        // their drop opening in the top band (the drop is not an exit).
        if (mask & SHAPE_N) {
            for (int x = 0; x < kRoomWidth; ++x) model.tiles[x] =
                (int)TileType::SOLID_WALL;
            model.tiles[kGapA] = model.tiles[kGapB] = (int)TileType::AIR;
            if ((mask & SHAPE_GATE) && (mask & SHAPE_2GAP)) {
            // A two-gap ceiling reaches the door through band 0: the top
            // corridor is a lobby, so an entry arriving at the OTHER gap still
            // finds the door. (The south edge keeps only the two carved cells
            // — widening it would drop the player into the next room's wall.)
            for (int x = kGapA; x <= kGapB; ++x) {
                model.tiles[x] = (int)TileType::AIR;
            }
        }
        if (mask & SHAPE_START) {
                for (int x = 2; x <= 6; ++x)
                    model.tiles[x] = (int)TileType::AIR;
            }
        }
        if (mask & SHAPE_S) {
            const int base = (kGenRows - 1) * kRoomWidth;
            for (int x = 0; x < kRoomWidth; ++x) model.tiles[base + x] =
                (int)TileType::SOLID_WALL;
            model.tiles[base + kGapA] = model.tiles[base + kGapB] =
                (int)TileType::AIR;
        }
    }
    if (mask & SHAPE_CHANNEL) {
        // Hot ceiling cells 1..7; cells 8/9 stay the N shaft, cell 0 is the
        // H exit. The floor is open water: crossing low on the raft is the
        // only safe route (row 1 is lethal wall).
        for (int x = 1; x <= 7; ++x) {
            model.tiles[1 * kRoomWidth + x] = (int)TileType::SOLID_WALL;
        }
        model.mid_band_type = 1;
        if (mask & SHAPE_2GAP) {
            // The 2-gap ceiling above must drop INTO the channel, not onto a
            // hot cell: open the same two cells in the hot row.
            model.tiles[1 * kRoomWidth + kGapA] = (int)TileType::AIR;
            model.tiles[1 * kRoomWidth + kGapB] = (int)TileType::AIR;
        }
        for (int x = 1; x < kRoomWidth; ++x) {
            model.tiles[(kGenRows - 1) * kRoomWidth + x] =
                (int)TileType::AIR;
        }
    }
    if (mask & SHAPE_WATER) {
        // Water goal: the bottom band is open, so the water strip shows and
        // kills; the miner waits on row 1 STANDING ON A ROCK (user rule
        // 2026-10-21 — a person to rescue does not swim or fly), and the raft
        // floats on another open cell so it never spawns inside the rock.
        for (int x = 1; x < kRoomWidth; ++x) {
            model.tiles[(kGenRows - 1) * kRoomWidth + x] =
                (int)TileType::AIR;
        }
        model.tiles[(kGenRows - 1) * kRoomWidth + kMinerCell] =
            (int)TileType::SOLID_WALL;
    }
    // Archetype interior (HERO-like normality): cells 1..7 only, applied
    // AFTER the functional carving, then the 2-gap corridor is re-opened.
    //
    // BAND-2 ARCHETYPES (user item 3, 2026-10-24): in a PLAIN room the
    // archetype's third row is drawn into band 2 by the 4-band expansion below
    // instead of into the floor band, so the room reads as a cave with ledges
    // rather than an aisle over a solid slab. Hazard rooms (gate / hot /
    // channel / water) keep the slab: their band 1 is the only way through, so
    // an open band 2 would let the player fly around a locked door or a hot
    // ceiling.
    const int arch = (mask >> kArchShift) & kArchMask;
    const bool bandArt = arch >= 1 && arch <= 7
            && !(mask & (SHAPE_GATE | SHAPE_CHANNEL | SHAPE_WATER | SHAPE_HOT));
    if (arch >= 1 && arch <= 7) {
        for (int row = 0; row < kGenRows; ++row) {
            if (row == 2 && bandArt) continue;   // → band 2, see the expansion
            for (int x = 0; x < kRoomWidth; ++x) {
                if (kArch[arch][row][x] == '#') {
                    model.tiles[row * kRoomWidth + x] =
                        (int)TileType::SOLID_WALL;
                }
            }
        }
    } else if (arch >= 8 && arch <= 14) {
        const char* pat = kArchHot[arch - 8];
        for (int x = 0; x < kRoomWidth; ++x) {
            if (pat[x] == '#') {
                model.tiles[1 * kRoomWidth + x] = (int)TileType::SOLID_WALL;
            }
        }
        model.mid_band_type = 1;
    }
    // --- EXIT GEOMETRY + CONNECTIVITY (user rules 2026-10-21) -------------
    // PF walls are one pattern per 48-line band, so an entry only works if
    // band 1 is open on the same column. The generator now:
    //   * forces the carved edge cells (WIDE = both corridor cells, NARROW =
    //     one), which is what makes consecutive links alternate;
    //   * opens band 1 across the span between the top and bottom cells, so
    //     the player can LINE UP (the "space in the middle band" a dogleg
    //     room needs) — never a straight empty fall;
    //   * gives a horizontal room its aisle from cell 0;
    //   * lets a gate keep only the door column open in band 1.
    {
        const int vA = (mask & SHAPE_2GAP) ? kGapA : kVertExitA;
        const int vB = (mask & SHAPE_2GAP) ? kGapB : kVertExitB;
        std::vector<int> nCells, sCells;
        if (mask & SHAPE_N) {
            model.tiles[vA] = (int)TileType::AIR;
            nCells.push_back(vA);
            if (mask & SHAPE_N1) {
                model.tiles[vB] = (int)TileType::SOLID_WALL;
            } else {
                model.tiles[vB] = (int)TileType::AIR;
                nCells.push_back(vB);
            }
        }
        if (mask & SHAPE_S) {
            const int base = (kGenRows - 1) * kRoomWidth;
            model.tiles[base + vA] = (int)TileType::AIR;
            sCells.push_back(vA);
            if (mask & SHAPE_S1) {
                model.tiles[base + vB] = (int)TileType::SOLID_WALL;
            } else {
                model.tiles[base + vB] = (int)TileType::AIR;
                sCells.push_back(vB);
            }
        }
        if (mask & SHAPE_WN) {
            for (int x = kGapA; x <= kGapB; ++x)
                model.tiles[x] = (int)TileType::AIR;
        }
        if (mask & SHAPE_WS) {
            const int base = (kGenRows - 1) * kRoomWidth;
            for (int x = kGapA; x <= kGapB; ++x)
                model.tiles[base + x] = (int)TileType::AIR;
        }
        int lo = kRoomWidth, hi = -1;
        for (int c : nCells) { if (c < lo) lo = c; if (c > hi) hi = c; }
        for (int c : sCells) { if (c < lo) lo = c; if (c > hi) hi = c; }
        if (mask & SHAPE_GATE) {
            // The keyed door is the ONLY passage: band 1 keeps just the first
            // corridor cell (the door column).
            hi = lo;
        }
        if (hi >= lo) {
            for (int x = lo; x <= hi; ++x) {
                model.tiles[1 * kRoomWidth + x] = (int)TileType::AIR;
            }
        }
        if (mask & SHAPE_H) {
            const int near = (hi >= lo) ? lo : 0;
            for (int x = 0; x <= near; ++x) {
                model.tiles[1 * kRoomWidth + x] = (int)TileType::AIR;
            }
        }
        if ((mask & SHAPE_GATE) && (mask & SHAPE_2GAP)) {
            // Top lobby: an entry arriving at the other gap still finds the
            // door (the south edge keeps the carved cells; widening it would
            // drop the player into the next room's wall).
            for (int x = kGapA; x <= kGapB; ++x) {
                model.tiles[x] = (int)TileType::AIR;
            }
        }
        if (mask & SHAPE_START) {
            for (int x = 2; x <= vA; ++x) model.tiles[x] = (int)TileType::AIR;
        }
    }
    if (arch && (mask & SHAPE_2GAP)) {
        model.tiles[1 * kRoomWidth + kGapA] = (int)TileType::AIR;
        model.tiles[1 * kRoomWidth + kGapB] = (int)TileType::AIR;
        if (mask & SHAPE_N) {
            model.tiles[kGapA] = (int)TileType::AIR;
            if (!(mask & SHAPE_N1)) model.tiles[kGapB] = (int)TileType::AIR;
        }
        if (mask & SHAPE_S) {
            const int base = (kGenRows - 1) * kRoomWidth;
            model.tiles[base + kGapA] = (int)TileType::AIR;
            if (!(mask & SHAPE_S1)) {
                model.tiles[base + kGapB] = (int)TileType::AIR;
            }
        }
    }
    // --- NO DEAD AIR POCKETS (user rule 2026-10-21) -----------------------
    // A band-1 air cell that cannot be reached from any band-0/2 opening (or
    // from the horizontal exit) is decoration the player can never use — the
    // HotComb leftover at cells 7/8 was the reported "nothing to do here"
    // room. Close every such component; the corridor and the aisle always
    // anchor to an edge, so they are never touched.
    {
        bool ink[3][kRoomWidth] = {};
        for (int b = 0; b < kGenRows; ++b)
            for (int x = 0; x < kRoomWidth; ++x)
                ink[b][x] = model.tiles[b * kRoomWidth + x]
                                == (int)TileType::AIR;
        bool seen[3][kRoomWidth] = {};
        for (int x = 0; x < kRoomWidth; ++x) {
            for (int b : {1}) {
                if (!ink[b][x] || seen[b][x]) continue;
                bool anchored = false;
                std::vector<std::pair<int, int>> comp, stack{{b, x}};
                seen[b][x] = true;
                while (!stack.empty()) {
                    auto [y, c] = stack.back();
                    stack.pop_back();
                    comp.push_back({y, c});
                    if ((y == 1 && c == 0 && (mask & SHAPE_H)) ||
                        (y > 0 && ink[y - 1][c]) ||
                        (y < kGenRows - 1 && ink[y + 1][c])) {
                        anchored = true;
                    }
                    for (int dy : {-1, 0, 1}) {
                        for (int dx : {-1, 0, 1}) {
                            if (std::abs(dx) + std::abs(dy) != 1) continue;
                            const int ny = y + dy, nx = c + dx;
                            if (ny < 0 || ny >= kGenRows || nx < 0
                                    || nx >= kRoomWidth) continue;
                            if (!ink[ny][nx] || seen[ny][nx]) continue;
                            seen[ny][nx] = true;
                            stack.push_back({ny, nx});
                        }
                    }
                }
                if (!anchored) {
                    for (auto [y, c] : comp) {
                        model.tiles[y * kRoomWidth + c] =
                            (int)TileType::SOLID_WALL;
                    }
                }
            }
        }
    }

    // --- THIN WALLS (user rule 2026-10-21) --------------------------------
    // The bomb punch removes a THIN wall — a solid cell with air on both
    // sides — so a decorative 1-cell pillar is a pointless bomb target. A
    // generated wall must be a RUN: an isolated cell is thickened on a side
    // that carries no path (vertical corridor / horizontal aisle / start
    // drop); if both sides carry the path, the decoration is removed. The
    // intentional bombable blocks live on ROOMS (asym patches), never here.
    {
        const int pa = (mask & SHAPE_2GAP) ? kGapA : kVertExitA;
        const int pb = (mask & SHAPE_2GAP) ? kGapB : kVertExitB;
        const int near = pa < pb ? pa : pb;
        const bool start = (mask & SHAPE_START) != 0;
        const int startNear = (mask & SHAPE_2GAP) ? kGapA : kVertExitA;
        // Is this cell part of a path the room needs (and so may not become
        // a wall)? The corridor spans every band; the horizontal aisle only
        // band 1; the spawn drop only bands 0/1.
        auto keep = [&](int band, int x) {
            if (x == pa || x == pb) return true;            // vertical corridor
            if ((mask & SHAPE_H) && band == 1 && x <= near) return true;
            if (start && band == 0 && x >= 2 && x <= startNear) return true;
            if (start && band == 1 && x == 4) return true;  // HotDrop column
            return false;
        };
        auto solid = [&](int band, int x) {
            return model.tiles[band * kRoomWidth + x]
                       != (int)TileType::AIR;
        };
        // BAND 1 ONLY (user report 2026-10-24, screenshot stuck_002.png): the
        // ceiling and floor rows are the VERTICAL APERTURES. Opening an
        // isolated cell there invents a hole the room below/above need not
        // have — the player fell through a 4/5 hole the neighbour's ceiling
        // walls, landed inside it and stopped falling. Decoration lives in the
        // walkable band, which is also the only one a bomb punch can reach.
        for (int band = 1; band < 2; ++band) {
            for (int x = 1; x < kRoomWidth - 1; ++x) {
                if (!solid(band, x) || solid(band, x - 1)
                        || solid(band, x + 1)) {
                    continue;                     // part of a run
                }
                const bool leftFree = !keep(band, x - 1);
                const bool rightFree = !keep(band, x + 1);
                int cand = -1;
                if (leftFree && !rightFree) cand = x - 1;
                else if (rightFree && !leftFree) cand = x + 1;
                else if (leftFree && rightFree) cand = (x < 5) ? x - 1 : x + 1;
                if (cand >= 0) {
                    model.tiles[band * kRoomWidth + cand] =
                        model.tiles[band * kRoomWidth + x];
                } else {
                    model.tiles[band * kRoomWidth + x] = (int)TileType::AIR;
                }
            }
        }
    }
    // N=4 (2026-10-24): one row per drawn band. The plan is built in three
    // rows (0 ceiling / 1 shaft / 2 floor+water); band 2 is DERIVED as the
    // vertical route's continuation — open only at the room's exit columns
    // (3/6 for a two-gap shape, 8/9 otherwise), walls everywhere else. So the
    // cave has two real walkable bands with no inserted AIR pad, and every
    // other band-1 column stays WALLED in band 2: that wall is exactly what
    // the whole-cave M1 strip needs (a locked door / async block paints one
    // band and requires the others walled at its column), which is why band 2
    // is NOT a copy of band 1 — a copy left the block scan with no legal cell
    // and level 7 lost its async room entirely.
    // Every planned shape takes this path, including the SHAPE_GATE ones: with
    // locked doors disabled (PlanFor: p.gate = false) the only gate shapes are
    // the PHASE corridors, whose blink is a band-1 PF cell on the corridor
    // column — the same column band 2 keeps open — so the blink still gates the
    // whole passage and no M1 strip is involved. A real LOCKED DOOR would have
    // to come back here: its strip may only be painted on band 1 (2-patch cap)
    // while band 2 must stay open for the descent, which needs the landing
    // design (enter one side, cross the door, descend on the other).
    {
        const int routeA = (mask & SHAPE_2GAP) ? kGapA : kVertExitA;
        const int routeB = (mask & SHAPE_2GAP) ? kGapB : kVertExitB;
        std::vector<int> three = model.tiles;   // rows 0,1,2
        model.tiles.assign(kRoomWidth * 4, (int)TileType::AIR);
        for (int x = 0; x < kRoomWidth; ++x) {
            model.tiles[0 * kRoomWidth + x] = three[0 * kRoomWidth + x];
            model.tiles[1 * kRoomWidth + x] = three[1 * kRoomWidth + x];
            const bool route = (x == routeA || x == routeB)
                    && three[1 * kRoomWidth + x] == (int)TileType::AIR;
            if (bandArt) {
                // The lower chamber: open, with the archetype's third row as
                // its ledges. Cells 0/1/7 stay SOLID on purpose — the outer
                // edge is a wall in every band (the H side link lives in band
                // 1 only) and the async block / door scan needs a column where
                // band 2 is solid (a strip paints ONE band; every band it does
                // not paint must be walled at its column, 2026-10-24).
                // A WATER shape keeps a NICHE above the miner's rock: the
                // miner stands on the floor band's top edge (y = 96 px for a
                // 4-band room), which is the LAST 12 lines of band 2 — with the
                // slab solid there the PF (priority) hid him inside the wall
                // ("the miner is inside the ground", user 2026-10-24, level 5
                // room 5). Cell +1 too: his 8-px sprite starts at px 39, so it
                // straddles two cells.
                // EVERY shape keeps the niche: the miner's room is not always
                // a water room (level 1's goal is a plain shape), and the gate
                // in convert now refuses any model where his body cell is
                // solid. Two cells because his 8-px sprite straddles them.
                const bool minerNiche = (x == kMinerCell || x == kMinerCell + 1);
                const bool pillar = (x == 0 || x == 1 || x == 7);
                const bool archWall = kArch[arch][2][x] == '#';
                model.tiles[2 * kRoomWidth + x] = (route || minerNiche
                        || (!pillar && !archWall))
                        ? (int)TileType::AIR : (int)TileType::SOLID_WALL;
            } else {
                // Water rooms take this path (bandArt is off for them), so the
                // miner niche has to be carved here.
                model.tiles[2 * kRoomWidth + x] = (route
                        || x == kMinerCell || x == kMinerCell + 1)
                        ? (int)TileType::AIR : (int)TileType::SOLID_WALL;
            }
            model.tiles[3 * kRoomWidth + x] = three[2 * kRoomWidth + x];
        }
        // wideBottom is a crunch room's ESCAPE below band 2: its floor is
        // band 3 (index 2), not only the cave floor (band 4) — a 2-cell hole
        // there was a death trap (user rule 2026-10-26: >= 4 cells).
        if (mask & SHAPE_WS) {
            for (int x = kGapA; x <= kGapB; ++x) {
                model.tiles[2 * kRoomWidth + x] = (int)TileType::AIR;
            }
        }
        model.height = 4;
    }
    return model;
}

// Deterministic integer mix: the layout's only source of (reproducible)
// variation. No RNG, no clock — two runs must be byte-identical.
unsigned LayoutMix(unsigned a, unsigned b) {
    unsigned h = a * 2654435761u ^ (b + 0x9E3779B9u);
    h ^= h >> 15;
    h *= 2246822519u;
    h ^= h >> 13;
    return h;
}

// LAYOUT (user rule 2026-10-24): the room GRID comes first, the exits follow
// from ADJACENCY (RoomShapeMask). A connected set of `rooms` cells is grown on
// a 5x5 lattice, then the GOAL room is moved to the end of the walk: it is the
// LEAF farthest from the start, because the miner stands there and the level
// ends by touching him — a goal room continues nowhere.
//
// Complexity RAMPS with the level (user rule 2026-10-24: the multi-block maze
// is a level-15+ shape of level; early levels stay corridors):
//   maxTouch 1 (levels < 6)  : a new cell may touch ONE placed cell -> corridor
//   maxTouch 2 (levels < 15) : a second touch is allowed -> one loop/branch
//   maxTouch 3 (levels 15+)  : free growth -> the drawn maze, where the
//                              approach to the goal can be reached two ways
std::vector<GridPos> LevelLayoutSalt(int level, int rooms, unsigned salt,
                                     bool* waterLeaf) {
    const int n = rooms < 2 ? 2 : rooms;
    const int maxTouch = level < 6 ? 1 : (level < 15 ? 2 : 3);
    bool used[kGridH][kGridW] = {};
    std::vector<GridPos> walk;
    walk.reserve(n);
    used[0][0] = true;                  // the start room (top-left)
    walk.push_back(GridPos{0, 0});
    auto touch = [&](int x, int y) {
        int t = 0;
        if (x > 0 && used[y][x - 1]) ++t;
        if (x + 1 < kGridW && used[y][x + 1]) ++t;
        if (y > 0 && used[y - 1][x]) ++t;
        if (y + 1 < kGridH && used[y + 1][x]) ++t;
        return t;
    };
    for (int step = 1; step < n; ++step) {
        if (level < 6) {
            // Levels 1-5 are a straight vertical corridor (the ramp the
            // user asked for): the stem just keeps going down, which also
            // guarantees the hazard roles have a vertical room to host.
            const GridPos last = walk.back();
            const GridPos down{last.x, last.y + 1};
            if (down.y < kGridH) {
                used[down.y][down.x] = true;
                walk.push_back(down);
                continue;
            }
        }
        std::vector<GridPos> cand;
        for (int y = 0; y < kGridH; ++y) {
            for (int x = 0; x < kGridW; ++x) {
                if (used[y][x]) continue;
                const int t = touch(x, y);
                if (t == 0 || t > maxTouch) continue;
                cand.push_back(GridPos{x, y});
            }
        }
        if (cand.empty()) {             // ramp too tight: relax to any touch
            for (int y = 0; y < kGridH; ++y) {
                for (int x = 0; x < kGridW; ++x) {
                    if (!used[y][x] && touch(x, y) > 0) {
                        cand.push_back(GridPos{x, y});
                    }
                }
            }
        }
        if (cand.empty()) break;        // lattice full (cannot happen <= 20)
        GridPos p;
        const GridPos stem{0, 1};
        bool stemmed = false;
        if (step == 1) {
            // The start room always opens DOWNWARD (a stem) before the layout
            // fans out: the drawn layouts start with `S` above a single room,
            // and it also guarantees a VERTICAL room early on, which the
            // hazard roles (hot band, phase blink) need to exist at all.
            for (const GridPos& c : cand) {
                if (c.x == stem.x && c.y == stem.y) { p = c; stemmed = true; }
            }
        }
        if (!stemmed) {
            p = cand[LayoutMix((unsigned)level + salt * 977u, (unsigned)step) % cand.size()];
        }
        used[p.y][p.x] = true;
        walk.push_back(p);
    }
    // Goal = the leaf (exactly one neighbour) farthest from the start.
    auto degree = [&](const GridPos& p) {
        int d = 0;
        if (p.x > 0 && used[p.y][p.x - 1]) ++d;
        if (p.x + 1 < kGridW && used[p.y][p.x + 1]) ++d;
        if (p.y > 0 && used[p.y - 1][p.x]) ++d;
        if (p.y + 1 < kGridH && used[p.y + 1][p.x]) ++d;
        return d;
    };
    auto dist = [&](const GridPos& p) {
        return std::abs(p.x) + std::abs(p.y);   // start is (0,0)
    };
    int best = -1;
    int bestD = -1;
    // User rule 2026-10-29: a water room has no entry at its bottom, so from
    // level 4 (water goals) the goal is a leaf whose one neighbour is NOT below.
    for (int pass = 0; pass < 2 && best < 0; ++pass) {
        for (int i = 1; i < (int)walk.size(); ++i) {
            if (degree(walk[i]) != 1) continue; // leaves only: the goal never
            if (pass == 0 && level >= 4 && walk[i].y + 1 < kGridH
                    && used[walk[i].y + 1][walk[i].x]) continue;
            const int d = dist(walk[i]);        // continues anywhere
            if (d > bestD) { bestD = d; best = i; }
        }
    }
    if (best > 0) {
        std::swap(walk[best], walk.back());     // the goal room is the LAST room
    }
    if (waterLeaf) {
        *waterLeaf = best > 0 && !(walk.back().y + 1 < kGridH
                                   && used[walk.back().y + 1][walk.back().x]);
    }
    return walk;
}

// First salt whose goal has nothing below it (salt 0 = the old layout).
std::vector<GridPos> LevelLayout(int level, int rooms) {
    std::vector<GridPos> walk;
    for (unsigned salt = 0; salt < 200; ++salt) {
        bool ok = true;
        walk = LevelLayoutSalt(level, rooms, salt, &ok);
        if (ok || level < 4) break;
    }
    return walk;
}

bool HasRoomAt(const std::vector<GridPos>& walk, int x, int y) {
    for (const GridPos& pos : walk) {
        if (pos.x == x && pos.y == y) {
            return true;
        }
    }
    return false;
}

// How the player FIRST enters room `i` of a level: BFS over the room grid from
// the start room (index 0). 1 = from the room ABOVE (he is going down), 2 =
// from the room BELOW (going up), 0 = from the side (or the start room).
// A tie between equally short routes prefers a vertical parent.
// User rule 2026-10-28: a hcrunch sits on band 3 where he arrives falling (time
// to react) and on band 2 where he arrives climbing; a room first entered from
// the side never hosts one.
int FirstEntry(const std::vector<GridPos>& walk, int i) {
    const int n = (int)walk.size();
    std::vector<int> dist(n, -1);
    std::vector<int> queue{0};
    dist[0] = 0;
    auto indexAt = [&](int x, int y) {
        for (int k = 0; k < n; ++k) {
            if (walk[k].x == x && walk[k].y == y) return k;
        }
        return -1;
    };
    static const int kDx[4] = {0, 0, -1, 1};
    static const int kDy[4] = {-1, 1, 0, 0};      // above, below, left, right
    for (size_t h = 0; h < queue.size(); ++h) {
        const GridPos& g = walk[queue[h]];
        for (int d = 0; d < 4; ++d) {
            const int k = indexAt(g.x + kDx[d], g.y + kDy[d]);
            if (k >= 0 && dist[k] < 0) {
                dist[k] = dist[queue[h]] + 1;
                queue.push_back(k);
            }
        }
    }
    if (i == 0 || dist[i] < 0) return 0;
    for (int d = 0; d < 2; ++d) {                  // vertical parent first
        const int k = indexAt(walk[i].x + kDx[d], walk[i].y + kDy[d]);
        if (k >= 0 && dist[k] == dist[i] - 1) return d == 0 ? 1 : 2;
    }
    return 0;
}

// --- 2026-10-20: per-room ROLE (the HERO-style variety) ---------------------
// The generated stage used to be one shape with a bat; a level now alternates
// hazard rooms and normal rooms, and the last room can be a WATER goal
// (raft/tentacle + miner). Thresholds grow with the level number.
enum class Role { Normal, Hot, Gate, WaterGoal, Phase, Hcrunch };

struct LevelPlan {
    bool hot = false;       // hot row-1 bands
    bool gate = false;      // keyed gate room
    bool water = false;     // water goal (last room)
    bool tentacle = false;  // water goal hazard (otherwise a raft)
    bool extra = false;     // second enemy in normal rooms
    bool phase = false;     // blinking gate (timing room)
    bool hcrunch = false;   // horizontal crunch band (object-free room)
    bool patch = false;     // solid async block in normal rooms (a ledge)
    bool patch2 = false;    // a second block, opposite side (same room)
    bool twogap = false;    // two-gap vertical links (route choice)
};

LevelPlan PlanFor(int level) {
    LevelPlan p;
    p.hot = level >= 3;
    p.water = level >= 4;
    // Locked doors are DISABLED (user report 2026-10-21: level 13 could not
    // be completed). The door is an M1 column stripe, so it may only sit on a
    // column walled in bands 0/2 — i.e. NOT on a vertical corridor — and the
    // corridor is the only vertical passage. A true locked door needs
    // per-PAIR exit columns (a redesign); until then the gate role is played
    // by the blinking PHASE corridor, which does gate the corridor legally.
    p.gate = false;
    p.tentacle = level >= 7;
    p.extra = level >= 9;
    p.phase = level >= 6;       // timing gate on the corridor (was >= 11)
    p.hcrunch = level >= 14;    // crunch band sweeps the row-1 prefix
    p.patch = level >= 7;       // async block, now and then in normal rooms
    p.patch2 = level >= 12;     // two blocks (one per side) in that room
    // Exit-count variety (user rule 2026-10-21): from level 6 alternate the
    // vertical link scheme. A two-gap level has TWO separate exits at the top
    // and at the bottom (cells 3 and 6); a plain level has ONE wide exit
    // (cells 8-9). Same shape library, so the 6-bit shape index still fits.
    p.twogap = level >= 6 && level % 2 == 0;   // 6, 8, 10, ... 20
    return p;
}

std::vector<Role> HazardCycle(const LevelPlan& p) {
    std::vector<Role> h;
    if (p.hot) h.push_back(Role::Hot);
    if (p.gate) h.push_back(Role::Gate);
    if (p.phase) h.push_back(Role::Phase);
    if (p.hcrunch) h.push_back(Role::Hcrunch);
    return h;
}

Role RoleForRoom(int roomIndex, int roomCount, const LevelPlan& p) {
    if (roomIndex == roomCount - 1) {
        return p.water ? Role::WaterGoal : Role::Normal;
    }
    if (roomIndex == 0 || roomIndex % 2 == 0) {
        return Role::Normal;              // hazards alternate with breathers
    }
    const std::vector<Role> h = HazardCycle(p);
    if (h.empty()) return Role::Normal;
    return h[((roomIndex - 1) / 2) % h.size()];
}

// Exit mask a room's SHAPE must carry (see the layout notes above).
int RoomShapeMask(int levelNumber, const std::vector<GridPos>& walk,
                  const GridPos& pos, int roomIndex, Role role,
                  bool twogap) {
    int mask = 0;
    if (twogap) mask |= SHAPE_2GAP;
    if (HasRoomAt(walk, pos.x, pos.y - 1)) mask |= SHAPE_N;
    if (HasRoomAt(walk, pos.x, pos.y + 1)) mask |= SHAPE_S;
    // Link `i` joins walk[i] -> walk[i+1]; a room's TOP uses link i-1 and its
    // BOTTOM uses link i, so alternating the width per link makes every
    // through-room's top/bottom differ (user rule 2026-10-21).
    if (levelNumber >= 6) {
        if ((mask & SHAPE_N) && (roomIndex - 1) % 2 == 0) mask |= SHAPE_N1;
        if ((mask & SHAPE_S) && roomIndex % 2 == 0) mask |= SHAPE_S1;
    }
    // Side openings come from ADJACENCY (user rule 2026-10-24). ONE bit covers
    // both sides: the playfield is reflected, cell 0 is drawn on both edges, so
    // a room with a single horizontal neighbour also shows a dead aperture on
    // its far side (the exit scan finds no room there and the player stops at
    // the edge — it cannot tear a transition).
    if (HasRoomAt(walk, pos.x - 1, pos.y)
            || HasRoomAt(walk, pos.x + 1, pos.y)) {
        mask |= SHAPE_H;
    }
    if (roomIndex == 0) mask |= SHAPE_START;   // the level's spawn room
    if (IsChannelRoom(levelNumber, walk, pos)) {
        mask |= SHAPE_CHANNEL;
    } else {
        // Phase keeps the plain corridor (band 2 open edge to edge); only the
        // keyed gate walls band 2 off.
        if (role == Role::Gate) mask |= SHAPE_GATE;
        if (role == Role::WaterGoal) mask |= SHAPE_WATER;
    }
    return mask;
}

int Lift(int value) {                 // a lighter wall colour for the row-1 band
    return value + 40 > 255 ? 255 : value + 40;
}

// One room's objects. The editor's caps are the contract: <= 2 objects per
// room (enemies + lamps + miner) and <= 1 element per tile row (MapCanvas
// kMaxRoomElements / ElementInRow, verify_build repeats the 2-object cap).
// Row = y/4 (rows 0/1/2), the same conversion convert uses.
void AddEnemy(RoomData& room, EnemyType type, float x, float y, float speed,
              float rangeMax, int dir = 1) {
    EnemyData e;
    e.type = (int)type;
    e.x = x;
    e.y = y;
    e.range_min = 0.0f;
    e.range_max = rangeMax;
    e.speed = speed;
    e.dir = dir;
    if (type == EnemyType::SPIDER && SpiderForcedDir(y) != 0)
        e.dir = SpiderForcedDir(y);     // never sweep out of the cave
    room.enemies.push_back(e);
}

int RowOf(float y) { return (int)y / 4; }

bool RowOccupied(const RoomData& room, int row) {
    for (const EnemyData& e : room.enemies) {
        if (RowOf(e.y) == row) return true;
    }
    for (const LampData& l : room.lamps) {
        if (RowOf(l.y) == row) return true;
    }
    return false;
}

int ObjectCount(const RoomData& room) {
    return (int)(room.enemies.size() + room.lamps.size());
}

// ---- placement primitives (user rules 2026-10-21) -------------------------
// A shape's tiles: 0 = air, non-zero = wall (a hot row-1 wall is still solid).
// Enemies and lamps must never sit inside a wall — the SNAKE is the documented
// exception (it lives in the wall and needs open air on the side it faces).
bool CellAir(const ModelData& m, int band, int cell) {
    return cell >= 0 && cell < kRoomWidth
        && m.tiles[band * kRoomWidth + cell] == 0;
}

// Nearest AIR cell of `band` to `prefer` (search outward), or -1 if the band is
// fully solid.
int NearestAir(const ModelData& m, int band, int prefer) {
    if (prefer < 0) prefer = 0;
    if (prefer >= kRoomWidth) prefer = kRoomWidth - 1;
    if (CellAir(m, band, prefer)) return prefer;
    for (int d = 1; d < kRoomWidth; ++d) {
        if (CellAir(m, band, prefer - d)) return prefer - d;
        if (CellAir(m, band, prefer + d)) return prefer + d;
    }
    return -1;
}

// User rule 2026-10-29 (no forced life loss): an enemy must not sit on the
// player's way through a vertical opening. A ceiling/floor row with only a few
// air cells is an EXIT GAP; a bat at the foot of the gap that drops in (or
// at its head, from below) is hit before the player can aim (the laser is
// horizontal) - found by the playbot on level 2 room 2 (bat under the gap).
// Prefer the nearest air cell at least 2 cells away from every exit gap of the
// rows above (band >= 1) and below (band <= h-2); fall back to NearestAir.
int NearestAirClear(const ModelData& m, int band, int prefer) {
    const int h = m.height;
    auto airCount = [&](int row) {
        int n = 0;
        for (int c = 0; c < kRoomWidth; ++c) n += CellAir(m, row, c) ? 1 : 0;
        return n;
    };
    std::vector<int> gaps;
    if (band >= 1 && airCount(0) <= 4) {
        for (int c = 0; c < kRoomWidth; ++c) if (CellAir(m, 0, c)) gaps.push_back(c);
    }
    if (band <= h - 2 && airCount(h - 1) <= 4) {
        for (int c = 0; c < kRoomWidth; ++c) if (CellAir(m, h - 1, c)) gaps.push_back(c);
    }
    auto clear = [&](int c) {
        if (!CellAir(m, band, c)) return false;
        for (int g : gaps) if (std::abs(g - c) <= 1) return false;
        return true;
    };
    if (prefer < 0) prefer = 0;
    if (prefer >= kRoomWidth) prefer = kRoomWidth - 1;
    if (clear(prefer)) return prefer;
    for (int d = 1; d < kRoomWidth; ++d) {
        if (prefer - d >= 0 && clear(prefer - d)) return prefer - d;
        if (prefer + d < kRoomWidth && clear(prefer + d)) return prefer + d;
    }
    return NearestAir(m, band, prefer);
}

// N=4 (2026-10-24): the PLANS speak three rows (0 ceiling / 1 shaft / 2 floor)
// but a generated model carries one row per drawn band, band 2 being the
// vertical route's continuation. Placement code that means "the floor / water
// row" must ask for this band, never use the literal 2 (a literal 2 now lands
// in the route shaft, where the cell is usually a wall).
int FloorBand(const ModelData& m) { return m.height > 3 ? m.height - 1 : 2; }
// Object y lives in DISPLAY ROW units of 12 px over the 144-px cave, so a band
// spans 12/height units (4 for a 3-row model, 3 for a 4-row one).
int BandUnits(const ModelData& m) { return m.height > 0 ? 12 / m.height : 4; }
// Where the raft waits (user 2026-10-28, level 11 room 8 / level 14 room 9: it
// sat beside the shaft, so the player dropped past it and it only led to a
// wall). The ferry starts moving RIGHT when ridden (the record has no dir), so
// it belongs in the LEFT half, under the column the player drops through: the
// first cell open from the ceiling down to the water, else the first open
// above the water, else any open water cell. -1 = no open water.
int RaftCell(const ModelData& m) {
    const int w = m.width, last = m.height - 1;
    auto air = [&](int b, int c) {
        return m.tiles[b * w + c] == (int)TileType::AIR;
    };
    for (int c = 1; c < w; ++c) {
        bool open = true;
        for (int b = 0; b <= last && open; ++b) open = air(b, c);
        if (open) return c;
    }
    for (int c = 1; c < w; ++c)
        if (air(last, c) && air(last - 1, c)) return c;
    for (int c = 1; c < w; ++c)
        if (air(last, c)) return c;
    return -1;
}
// The raft's authored y: the kernel floats it on the water surface (line 132,
// plank top 131), so author it there - the editor and the stage then show it
// where the game draws it, not a tile inside the water band.
constexpr float kRaftY = 131.0f / 12.0f;

float BandY(const ModelData& m, int band) {
    const int u = BandUnits(m);
    return (float)(band * u + (band == 0 ? 1 : u / 2));
}

// A lamp hangs in a GAP, on the side next to a wall (user rule 2026-10-21):
// an air cell whose left or right neighbour is a REAL wall. The screen edge
// and the reflected centre seam are open space, not walls, so the test is
// explicit about the cell range (a lamp at cell 9 against the mirror is
// floating — user report: "between the tiles"). Returns cell or -1.
int LampCell(const ModelData& m, int band, int prefer) {
    if (prefer < 0) prefer = 0;
    if (prefer >= kRoomWidth) prefer = kRoomWidth - 1;
    auto wallAt = [&](int c) {
        return c >= 0 && c < kRoomWidth && !CellAir(m, band, c);
    };
    for (int d = 0; d < kRoomWidth; ++d) {
        for (int s = 0; s < 2; ++s) {
            const int c = prefer + (s ? d : -d);
            if (!CellAir(m, band, c)) continue;
            if (wallAt(c - 1) || wallAt(c + 1)) return c;
        }
    }
    return -1;
}

// --- completability guard (user 2026-10-21) --------------------------------
// A generated room must let the player THROUGH: every way in (top edge, and
// the row-1 cell 0 horizontal edge) must reach a way out (bottom edge / the
// horizontal edge) through air. PF walls span the full 48-line band, so a
// band-1 wall that misses the vertical corridor seals the room — exactly the
// family that soft-locked level 13. Phase/hcrunch cells are gated at run time
// and therefore count as passable; a LOCKED door never sits on the generator's
// models (the door is a room patch).
// Returns an empty string when the room is fine, else a short description.
std::string RoomConnectivityProblem(const ModelData& m) {
    auto air = [&](int band, int x) { return CellAir(m, band, x); };
    // Height-aware (N=4): the south edge is the LAST band and the pads add a
    // band in the middle, so a generated 4-row model is checked as it ships.
    const int bands = (m.width > 0)
        ? (int)m.tiles.size() / m.width : 0;
    if (bands < 3) return "";
    const int last = bands - 1;
    std::vector<std::pair<int, int>> ins, outs;
    for (int x = 0; x < kRoomWidth; ++x) {
        if (air(0, x)) ins.push_back({0, x});
        if (air(last, x)) outs.push_back({last, x});
    }
    if (air(1, 0)) {
        ins.push_back({1, 0});
        outs.push_back({1, 0});
    }
    if (ins.empty() || outs.empty()) return "";   // sentinel / dead end
    for (const auto& start : ins) {
        bool seen[8][hero::kRoomWidth] = {};
        std::vector<std::pair<int, int>> stack{start};
        seen[start.first][start.second] = true;
        while (!stack.empty()) {
            auto [y, x] = stack.back();
            stack.pop_back();
            static const int dy[4] = {1, -1, 0, 0};
            static const int dx[4] = {0, 0, 1, -1};
            for (int k = 0; k < 4; ++k) {
                const int ny = y + dy[k], nx = x + dx[k];
                if (ny < 0 || ny >= bands || nx < 0
                        || nx >= kRoomWidth) continue;
                if (seen[ny][nx] || !CellAir(m, ny, nx)) continue;
                seen[ny][nx] = true;
                stack.push_back({ny, nx});
            }
        }
        bool reaches = false;
        for (const auto& goal : outs) {
            if (seen[goal.first][goal.second]) { reaches = true; break; }
        }
        if (!reaches) {
            return "entry cell (" + std::to_string(start.first) + ","
                 + std::to_string(start.second) + ") reaches no exit";
        }
    }
    return "";
}

void FillRoomObjects(int levelNumber, int roomIndex, int roomCount, Role role,
                     const LevelPlan& plan, RoomData& room,
                     const ModelData& shape,
                     bool roomIsKeyHost = false, int arch = 0) {
    if (roomIndex == roomCount - 1) {
        if (role == Role::WaterGoal) {
            // Water goal: the miner waits above the water; the raft ferries
            // (early levels) or a tentacle guards the surface (level 7+).
            room.bottom_band = true;
            room.bottom_r = 24;
            room.bottom_g = 88;
            room.bottom_b = 208;
            if (plan.tentacle) {
                // On open water: the row may carry the miner rock / two-gap
                // walls, so snap to the nearest air cell (the water band).
                const int tcell = NearestAir(shape, FloorBand(shape), 5);
                if (tcell >= 0) {
                    AddEnemy(room, EnemyType::TENTACLE, (float)(tcell * 2),
                             BandY(shape, FloorBand(shape)), 1.0f, 0.0f);
                }
            }
            // No RAFT here (user report 2026-10-24: "the raft is useless"): the
            // player has a jetpack, so open water in a goal room is always
            // flyable and the ferry is pure decoration. The raft only earns its
            // slot where the ceiling forces a LOW crossing — the CHANNEL rooms
            // (hot row 1), which keep theirs.
        } else if (roomCount > 1 && levelNumber >= 2) {
            // Goal room: the miner sits at x=4, so an enemy past it (the old
            // wall snake at cell 0) was never fought (user rule 2026-10-21).
            // From level 2 one bat guards the APPROACH corridor (cell 8),
            // which also keeps the 2-room levels distinct (L1 is clean).
            const int cell = NearestAirClear(shape, 1, 8);
            if (cell >= 0) {
                AddEnemy(room, EnemyType::BAT, (float)(cell * 2),
                         (levelNumber % 2) ? 4.0f : 5.0f,
                         1.25f + 0.25f * (levelNumber % 4), 13.0f);
            }
        }
        return;
    }
    if (roomIndex == 0) {
        // Start room: NO enemies (user rule 2026-10-21) — the player spawns
        // here and an enemy behind spawn is never met. Hot walls are allowed
        // on advanced levels (see the archetype pick in Build20LevelStage),
        // and async blocks sit near the exit gap.
        return;
    }
    if (role == Role::Gate || role == Role::Phase) {
        // Gate/phase cell = row 1 (band 1). A bat in band 0 sits on the fall
        // line: crossing cost two lives, the gate crush and then the bat
        // (screenshots/bugs/enemy_double_kill). So the generator PREFERS the
        // floor band, leaving band 2 empty between the gate and the enemy
        // (user ruling 2026-10-26), on a column away from the gate's own.
        // Fallback: band 0, then nothing. Hand-authored rooms are not blocked.
        const int fb = FloorBand(shape);
        int cell = NearestAirClear(shape, fb, 8);
        int band = fb;
        if (cell < 0) {
            cell = NearestAirClear(shape, 0, 8);
            band = 0;
        }
        if (cell >= 0) {
            AddEnemy(room, EnemyType::BAT, (float)(cell * 2),
                     BandY(shape, band),
                     1.25f + 0.25f * (levelNumber % 4), 13.0f);
        }
        return;
    }
    if (role == Role::Hcrunch) {
        // Convert rule: an hcrunch room has NO objects (the band owns the
        // sprite slot), so this room is empty on purpose.
        return;
    }
    if (role == Role::Hot) {
        // HOT rooms: NO middle-band objects (user rule 2026-10-21) — the
        // other two bands may each carry one. The gap archetypes block the
        // CENTRE (row 1), so the guards go on the OPEN cells of bands 0/2
        // near that gap — never inside the band-0/2 walls (user report
        // 2026-10-21: a bat inside the wall at level 3 room 2).
        const int hidx = (arch >= 8 && arch <= 14) ? arch - 8 : 0;
        const int gapCell = kArchHotGapX[hidx] / 2;
        const int bcell = NearestAirClear(shape, 0, gapCell);
        if (bcell >= 0) {
            AddEnemy(room, EnemyType::BAT, (float)(bcell * 2),
                     BandY(shape, 0),
                     1.25f + 0.25f * (levelNumber % 4), 13.0f);
        }
        if (levelNumber >= 5) {
            const int scell = NearestAir(shape, FloorBand(shape),
                                         gapCell == 3 ? 6 : 3);
            if (scell >= 0) {
                AddEnemy(room, EnemyType::SPIDER, (float)(scell * 2),
                         BandY(shape, FloorBand(shape)),
                         1.0f + 0.25f * (levelNumber % 4), 8.0f);
            }
        }
        return;
    }
    // Normal room: bat/lamp. A LAMP only matters where the dark mask reaches
    // (rooms 0-7), so deeper rooms get a bat.
    // Normal rooms: one object in the middle band (the shaft, cell 8) and, from
    // level 5, a second on ANOTHER band (top corridor, cell 8) — 2 objects per
    // room, one per band, as the user asked (2026-10-21). Flicker is the
    // kernel's job (one sprite), not a reason to starve the rooms.
    if (roomIndex % 2 == 1 || roomIndex >= 8) {
        const int cell = NearestAirClear(shape, 1, 8);
        if (cell >= 0) {
            AddEnemy(room, EnemyType::BAT, (float)(cell * 2),
                     (levelNumber % 2) ? 4.0f : 5.0f,
                     1.25f + 0.25f * (levelNumber % 4), 13.0f);
        }
    } else {
        // A lamp hangs in a gap next to a wall (user rule 2026-10-21): a lamp
        // floating in open air reads as "between the tiles" (level 4 room 3).
        // The lamp must hang in a gap NEXT TO A WALL (user rule 2026-10-21):
        // a lamp floating in the open reads as "between the tiles". The maze
        // layout has rooms whose band 1 is one wide aisle, so if no legal cell
        // exists in band 1 try band 0 and otherwise SKIP the lamp — the old
        // NearestAir fallback put it in the open.
        int cell = LampCell(shape, 1, 8);
        int lampBand = 1;
        if (cell < 0) {
            cell = LampCell(shape, 0, 8);
            lampBand = 0;
        }
        if (cell >= 0) {
            LampData lamp;
            lamp.x = (float)(cell * 2);
            lamp.y = BandY(shape, lampBand);
            lamp.lit = true;
            room.lamps.push_back(lamp);
        }
    }
    // From level 5 a second object on another band. Skip the room right
    // before a gate: it is the key host (the key needs a free slot, and a key
    // in the START room would break the clean-spawn rule).
    //
    // Pick the first band that ACTUALLY has air (2026-10-24): the maze shapes
    // have solid ceilings/ledges, so "row 0 is free" no longer implies an air
    // cell there — the old if/else chain then placed nothing at all.
    if (levelNumber >= 5 && !roomIsKeyHost) {
        for (const int band : {0, FloorBand(shape), 2}) {
            if (RowOccupied(room, band)) continue;
            const int cell = NearestAir(shape, band, 8);
            if (cell < 0) continue;
            AddEnemy(room, EnemyType::SPIDER, (float)(cell * 2),
                     BandY(shape, band),
                     1.0f + 0.25f * (levelNumber % 4), 8.0f);
            break;
        }
    }
}


// ---- stage REACHABILITY (user report 2026-10-25: "level 8 looks impossible") --
// The playfield is MIRRORED, so a room is two chambers (the left half and its
// mirror) that only join where the centre seam is open across a whole band.
// Exits keep the side: a westward move lands in the neighbour's RIGHT chamber,
// an eastward one in its LEFT, and a vertical link keeps the chamber. A level
// whose rooms all have a centre wall in the bands the player can use therefore
// splits into parallel universes and the miner is simply unreachable — the
// per-room check (RoomConnectivityProblem) cannot see that, it only ever looks
// at one half. This walks the whole level on the 20-column FULL map:
//   * air = model cell 0 (a hot/solid cell is a wall); a 3-row model is padded
//     with the open band 2 exactly like convert_room.band_map();
//   * a solid async patch (M1 left strip -> full col c, ball right strip ->
//     full col 10+c) costs ONE BOMB to cross; locked-door / phase / crunch
//     cells are gated at run time and count as passable;
//   * vertical links need the same full column open on both sides; side links
//     need the same band open on the edge column (0 <-> 19);
//   * the drop-in is the START room, band 0, display col 8 (full col 4).
// Returns the cheapest number of bombs to reach the miner's room (-1 = never)
// and the rooms in order of discovery (for the generator's repair loop).
constexpr int kMaxBombsPerLevel = 1;    // the player carries BOMBS_MAX (5); the
                                        // start room's block (user rule
                                        // 2026-10-21) is the one bomb a level
                                        // may ask for

// A SPIDER hangs at a fixed x and bobs 24 px down (then dwells at the top), so
// the columns it covers are a timing hazard the player cannot steer around when
// they are the passage itself: level 8 room 3 parked one beside the only shaft
// (user report 2026-10-25: "the only way I can continue is dying by the enemy
// below the path"). Its danger zone is every full-map cell a colliding player
// can occupy: CheckEnemyHit overlaps when RoomX - EX is in [-6, 7], i.e. the
// lit span [EX-13, EX+6], plus 2 px of margin, over the bands the bob sweeps.
// The route search charges kDangerCost per such cell so it avoids them when
// it can and reports the rooms it had to cross.
constexpr int kDangerCost = 1000;

struct ReachResult {
    int bombs = -1;
    std::vector<int> dangerRooms;   // room INDEXES whose spider the route crosses
    std::vector<int> order;     // room INDEXES, nearest first
    std::vector<int> crossed;   // room INDEXES of the patches on the cheapest route
    // Power-cell planning (2026-10-26): the cheapest route in ESTIMATED PLAY
    // TIME (see kRoute* below), start -> miner, one node per step. `cost` is
    // the cumulative estimate at that node.
    struct RouteNode { int room, band, col, cost; };
    std::vector<RouteNode> route;
    // Every (room, band, full col) the player can stand in with no bomb and no
    // spider on the way (extra miners must sit in one of these).
    std::set<std::tuple<int, int, int>> reach;
    // Rooms whose SOLID strip cannot be bombed (nowhere to stand on its centre
    // side, see the strip loop): the grid treats it as a wall.
    std::vector<int> deadStrips;
};

// Route time model (heuristic - the timer is 120 steps of 60 frames = 120 s and
// nothing in the generator can play the level, so it estimates). One full-map
// column is 8 px at 1 px/frame, one band about 30 frames of jet/fall, and a
// human needs roughly kRouteHuman x the ideal time plus a look-around at every
// room. Units are frames. tools/stage_reach.py route_segments() carries the
// same constants as the independent guard; tune them in BOTH.
constexpr int kRouteHuman = 3;
constexpr int kRouteStepH = 8 * kRouteHuman;
constexpr int kRouteStepV = 30 * kRouteHuman;
constexpr int kRouteRoom = 240;             // 4 s per room entered
constexpr int kCellBudget = 90 * 60;        // refill before a segment passes 90 s
constexpr int kCellLead = 80 * 60;          // ... aiming for ~80 s after the last (latest host keeps cells few)
constexpr int kBarSeconds = 120;
// An extra miner stands with his feet exactly on the ground: his 9 art rows end
// on the band's last line, so his top is 9 px above the band edge - for the floor
// band (2) that is 99 px = stage y 8.25 (the editor snaps to y = 3 * band + 2.25).
inline float ExtraMinerY() { return 8.25f; }

ReachResult AnalyseReach(const LevelData& lv,
                         const std::vector<ModelData>& models) {
    ReachResult out;
    const int n = (int)lv.rooms.size();
    if (n == 0) return out;
    auto modelOf = [&](int id) -> const ModelData* {
        for (const auto& m : models) {
            if (m.id == id) return &m;
        }
        return nullptr;
    };
    struct Grid {
        std::vector<std::vector<char>> air;     // [band][full col]
        std::set<std::pair<int, int>> bomb;     // (band, full col)
        std::set<std::pair<int, int>> danger;   // spider footprint
        int bands = 0;
    };
    std::vector<Grid> grids(n);
    std::map<std::pair<int, int>, int> at;
    for (int i = 0; i < n; ++i) {
        const RoomData& r = lv.rooms[i];
        at[{r.room_x, r.room_y}] = i;
        const ModelData* m = modelOf(r.model_id);
        if (!m || m->width <= 0) return out;
        std::vector<int> rows;                  // band -> model row (-1 = pad)
        const int h = (int)m->tiles.size() / m->width;
        if (h == 3) rows = {0, 1, -1, 2}; else for (int b = 0; b < h; ++b) rows.push_back(b);
        Grid& g = grids[i];
        g.bands = (int)rows.size();
        g.air.assign(g.bands, std::vector<char>(20, 0));
        for (int b = 0; b < g.bands; ++b) {
            for (int f = 0; f < 20; ++f) {
                const int c = f < 10 ? f : 19 - f;
                g.air[b][f] = rows[b] < 0
                    || m->tiles[rows[b] * m->width + c] == (int)TileType::AIR;
            }
        }
        for (const EnemyData& e : r.enemies) {
            if (e.type != (int)EnemyType::SPIDER) continue;
            const int c4 = (int)std::lround(e.x) * 4;
            const int ex = c4 + (c4 < 11 ? 4 : 7);           // enemy_x_px
            const int top = (int)std::lround(e.y * 12.0f);
            // dir < 0 sweeps UP from y (kernel DeriveEnemyY), else down
            const int up = e.dir < 0 ? 24 : 0;
            const int b0 = std::max(0, std::min(g.bands - 1, (top - up) / 36));
            const int b1 = std::max(0, std::min(g.bands - 1,
                                                (top + 24 - up + 14) / 36));
            const int f0 = std::max(0, (ex - 15) / 8);
            const int f1 = std::min(19, (ex + 8) / 8);
            for (int b = b0; b <= b1; ++b) {
                for (int f = f0; f <= f1; ++f) g.danger.insert({b, f});
            }
        }
    }
    // Bomb strips (second loop: it needs every room position). Three kinds are a
    // plain WALL: the dead-side PLUG (left M1 strip at col 0 / right ball strip at
    // col 9) with no room behind it (bank1 gate, 2026-10-26), and a strip nobody can
    // BOMB. The blast window is centred 7 px LEFT of the player (BombX = RoomX,
    // visible left = BombX - 7, +-2 display columns), so a player on the OUTER side
    // of a strip is always 2 columns short - measured on the real ROM (level 18, the
    // start room's block: RoomX 49 left of it never sets the strip's dead bit, RoomX
    // 66 right of it does). A strip can only be bombed from its CENTRE side: the
    // left (M1) strip at cell l from cells l+1/l+2, the right (ball) strip at full
    // column F from F-1/F-2, standing on a solid cell, in a cell the player reaches
    // without crossing any strip. Interior strips that pass this stay bombable.
    struct Strip { int room, band, col, side; };
    std::vector<Strip> strips;
    for (int i = 0; i < n; ++i) {
        const RoomData& r = lv.rooms[i];
        Grid& g = grids[i];
        const ModelData* m = modelOf(r.model_id);
        const int h = (int)m->tiles.size() / m->width;
        const bool west = at.count({r.room_x - 1, r.room_y}) > 0;
        const bool east = at.count({r.room_x + 1, r.room_y}) > 0;
        for (const auto& pt : r.asym_patches) {
            if ((int)pt.size() < 3) continue;
            if (pt[2] != (int)TileType::SOLID_WALL) continue;   // door: gated
            const int side = pt.size() > 3 ? pt[3] : 0;
            int band = pt[0];
            if (h == 3 && band >= 2) ++band;
            const int col = side == 1 ? pt[1] : 10 + pt[1];
            const bool edge = pt[1] == (side == 1 ? 0 : 9);   // the dead-side plug cell
            if (edge && !(side == 1 ? west : east)) {
                if (band >= 0 && band < g.bands) g.air[band][col] = 0;
                continue;
            }
            strips.push_back({i, band, col, side});
        }
    }
    {
        // reach with EVERY strip a wall (no spider zones, no bombs)
        for (const Strip& st : strips) grids[st.room].air[st.band][st.col] = 0;
        std::set<std::tuple<int, int, int>> seen;
        std::vector<std::tuple<int, int, int>> stack;
        const int s0 = std::max(0, std::min(n - 1, lv.start_room));
        int f0 = 4;
        for (int f : {4, 3, 5, 2, 6, 7, 8, 9}) {
            if (grids[s0].air[0][f]) { f0 = f; break; }
        }
        seen.insert({s0, 0, f0});
        stack.push_back({s0, 0, f0});
        while (!stack.empty()) {
            const auto [ri, b, f] = stack.back();
            stack.pop_back();
            const RoomData& r = lv.rooms[ri];
            const Grid& g = grids[ri];
            auto go = [&](int nr, int nb, int nf) {
                const Grid& ng = grids[nr];
                if (nb < 0 || nb >= ng.bands || nf < 0 || nf > 19) return;
                if (!ng.air[nb][nf] || ng.danger.count({nb, nf})) return;
                if (seen.insert({nr, nb, nf}).second) stack.push_back({nr, nb, nf});
            };
            go(ri, b + 1, f); go(ri, b - 1, f); go(ri, b, f + 1); go(ri, b, f - 1);
            if (b == g.bands - 1) {
                const auto o = at.find({r.room_x, r.room_y + 1});
                if (o != at.end()) go(o->second, 0, f);
            }
            if (b == 0) {
                const auto o = at.find({r.room_x, r.room_y - 1});
                if (o != at.end()) go(o->second, grids[o->second].bands - 1, f);
            }
            if (b == 1 || b == 2) {
                if (f == 19) {
                    const auto o = at.find({r.room_x + 1, r.room_y});
                    if (o != at.end()) go(o->second, b, 0);
                }
                if (f == 0) {
                    const auto o = at.find({r.room_x - 1, r.room_y});
                    if (o != at.end()) go(o->second, b, 19);
                }
            }
        }
        for (const Strip& st : strips) {
            const Grid& g = grids[st.room];
            bool ok = false;
            for (int d = 1; d <= 2 && !ok; ++d) {
                const int f = st.side == 1 ? st.col + d : st.col - d;
                if (f < 0 || f > 19) continue;
                for (int b = 0; b + 1 < g.bands && !ok; ++b) {
                    if (g.air[b][f] && !g.air[b + 1][f]
                            && seen.count({st.room, b, f})) ok = true;
                }
            }
            if (ok) {
                grids[st.room].air[st.band][st.col] = 1;
                grids[st.room].bomb.insert({st.band, st.col});
            } else {
                out.deadStrips.push_back(st.room);
            }
        }
    }
    // Dijkstra over (room, band, full col); crossing a patch cell costs 1.
    using Node = std::tuple<int, int, int>;
    using Item = std::pair<int, Node>;
    std::map<Node, int> best;
    std::map<Node, Node> parent;
    std::priority_queue<Item, std::vector<Item>, std::greater<Item>> pq;
    const int s = std::max(0, std::min(n - 1, lv.start_room));
    int sf = 4;
    for (int f : {4, 3, 5, 2, 6, 7, 8, 9}) {
        if (grids[s].air[0][f]) { sf = f; break; }
    }
    best[{s, 0, sf}] = 0;
    pq.push({0, {s, 0, sf}});
    std::vector<char> seenRoom(n, 0);
    int goal = std::max(0, std::min(n - 1, lv.miner_room));
    while (!pq.empty()) {
        const auto [cost, node] = pq.top();
        pq.pop();
        const auto it = best.find(node);
        if (it == best.end() || it->second < cost) continue;
        const auto [ri, b, f] = node;
        if (!seenRoom[ri]) { seenRoom[ri] = 1; out.order.push_back(ri); }
        if (cost == 0) out.reach.insert(node);
        if (ri == goal && out.bombs < 0) {
            out.bombs = cost % kDangerCost;
            Node cur = node;
            while (true) {
                const auto [cr, cb, cf] = cur;
                if (grids[cr].bomb.count({cb, cf})) out.crossed.push_back(cr);
                if (grids[cr].danger.count({cb, cf})) out.dangerRooms.push_back(cr);
                const auto pi = parent.find(cur);
                if (pi == parent.end()) break;
                cur = pi->second;
            }
        }
        const RoomData& r = lv.rooms[ri];
        auto go = [&](int nr, int nb, int nf) {
            const Grid& g = grids[nr];
            if (nb < 0 || nb >= g.bands || nf < 0 || nf > 19) return;
            if (!g.air[nb][nf]) return;
            const int c = cost + (g.bomb.count({nb, nf}) ? 1 : 0)
                               + (g.danger.count({nb, nf}) ? kDangerCost : 0);
            const Node nn{nr, nb, nf};
            const auto bi = best.find(nn);
            if (bi != best.end() && bi->second <= c) return;
            best[nn] = c;
            parent[nn] = node;
            pq.push({c, nn});
        };
        const Grid& g = grids[ri];
        go(ri, b + 1, f); go(ri, b - 1, f); go(ri, b, f + 1); go(ri, b, f - 1);
        if (b == g.bands - 1) {
            const auto o = at.find({r.room_x, r.room_y + 1});
            if (o != at.end()) go(o->second, 0, f);
        }
        if (b == 0) {
            const auto o = at.find({r.room_x, r.room_y - 1});
            if (o != at.end()) go(o->second, grids[o->second].bands - 1, f);
        }
        if (b == 1 || b == 2) {
            if (f == 19) {
                const auto o = at.find({r.room_x + 1, r.room_y});
                if (o != at.end()) go(o->second, b, 0);
            }
            if (f == 0) {
                const auto o = at.find({r.room_x - 1, r.room_y});
                if (o != at.end()) go(o->second, b, 19);
            }
        }
    }
    // Second pass: the same graph weighed in estimated play time (above). The
    // route visits every EXTRA MINER first (nearest first), then the goal. Spider
    // zones are walled off here (the first pass already reports them); a bomb
    // patch costs a few seconds.
    if (out.bombs >= 0) {
        std::vector<Node> pending;                  // extra miners: stand cells
        for (int i = 0; i < n; ++i) {
            for (const EnemyData& e : lv.rooms[i].enemies) {
                if (e.type != (int)EnemyType::EXTRA_MINER) continue;
                const int vis = (int)std::lround(e.x) * 4;    // visible left edge
                const int band = std::max(0, std::min(grids[i].bands - 1,
                                              (int)std::lround(e.y * 12.0f) / 36));
                pending.push_back({i, band, std::min(19, (vis + 3) / 8)});
            }
        }
        Node cur{s, 0, sf};
        long base = 0;
        std::vector<ReachResult::RouteNode> route{{s, 0, sf, 0}};
        bool ok = true;
        while (ok) {
            const bool finalLeg = pending.empty();
            std::map<Node, long> tbest;
            std::map<Node, Node> tparent;
            using TItem = std::pair<long, Node>;
            std::priority_queue<TItem, std::vector<TItem>, std::greater<TItem>> tq;
            tbest[cur] = base;
            tq.push({base, cur});
            std::optional<Node> reached;
            while (!tq.empty() && !reached) {
                const auto [cost, node] = tq.top();
                tq.pop();
                const auto ti = tbest.find(node);
                if (ti == tbest.end() || ti->second < cost) continue;
                const auto [ri, b, f] = node;
                if (finalLeg ? ri == goal
                             : std::find(pending.begin(), pending.end(), node)
                                   != pending.end()) {
                    reached = node;
                    break;
                }
                const RoomData& r = lv.rooms[ri];
                auto go = [&](int nr, int nb, int nf, int w) {
                    const Grid& g = grids[nr];
                    if (nb < 0 || nb >= g.bands || nf < 0 || nf > 19) return;
                    if (!g.air[nb][nf] || g.danger.count({nb, nf})) return;
                    const long c = cost + w + (g.bomb.count({nb, nf}) ? 600 : 0);
                    const Node nn{nr, nb, nf};
                    const auto bi = tbest.find(nn);
                    if (bi != tbest.end() && bi->second <= c) return;
                    tbest[nn] = c;
                    tparent[nn] = node;
                    tq.push({c, nn});
                };
                const Grid& g = grids[ri];
                go(ri, b + 1, f, kRouteStepV); go(ri, b - 1, f, kRouteStepV);
                go(ri, b, f + 1, kRouteStepH); go(ri, b, f - 1, kRouteStepH);
                if (b == g.bands - 1) {
                    const auto o = at.find({r.room_x, r.room_y + 1});
                    if (o != at.end()) go(o->second, 0, f, kRouteRoom);
                }
                if (b == 0) {
                    const auto o = at.find({r.room_x, r.room_y - 1});
                    if (o != at.end()) go(o->second, grids[o->second].bands - 1, f, kRouteRoom);
                }
                if (b == 1 || b == 2) {
                    if (f == 19) {
                        const auto o = at.find({r.room_x + 1, r.room_y});
                        if (o != at.end()) go(o->second, b, 0, kRouteRoom);
                    }
                    if (f == 0) {
                        const auto o = at.find({r.room_x - 1, r.room_y});
                        if (o != at.end()) go(o->second, b, 19, kRouteRoom);
                    }
                }
            }
            if (!reached) { ok = false; break; }
            std::vector<ReachResult::RouteNode> leg;
            Node walk = *reached;
            while (!(walk == cur)) {
                const auto [cr, cb, cf] = walk;
                leg.push_back({cr, cb, cf, (int)tbest[walk]});
                walk = tparent[walk];
            }
            std::reverse(leg.begin(), leg.end());
            route.insert(route.end(), leg.begin(), leg.end());
            if (finalLeg) break;
            cur = *reached;
            base = tbest[cur];
            pending.erase(std::find(pending.begin(), pending.end(), cur));
        }
        if (ok) out.route = route;
    }
    return out;
}


// EXTRA MINERS (user request 2026-10-26: up to three to rescue, the level ends
// once all are taken). Ramp: levels 7-13 carry one extra miner, 14-20 two; the
// level's own miner (the goal room) is the last. An extra miner is an enemy
// record of type 15 standing on the floor band like the level's own miner: the
// cells he occupies are air at band 2, the cell under his feet is solid, he is
// reachable without a bomb or a spider zone, and at most two exist per level in
// rooms of DIFFERENT index parity (the kernel keeps one "still to rescue" bit
// per parity). Rooms are spread along the route (1/3 and 2/3 of the order the
// search first visits them). Returns the miners placed (0 = no host room: the
// level keeps only its own miner; tools/test_generator.py counts the shortfalls).
int PlaceExtraMiners(LevelData& lv, const std::vector<ModelData>& models,
                     int levelNumber) {
    const int want = levelNumber >= 14 ? 2 : (levelNumber >= 7 ? 1 : 0);
    if (want == 0) return 0;
    const ReachResult rr = AnalyseReach(lv, models);
    if (rr.bombs < 0) return -1;
    auto modelOf = [&](int id) -> const ModelData* {
        for (const auto& m : models) {
            if (m.id == id) return &m;
        }
        return nullptr;
    };
    struct Spot { int room, col, evict; };
    // The best stand cell of a room, or room = -1. A full room (2 objects, most
    // rooms from level 7) gives up one plain enemy to host the miner.
    auto spotIn = [&](int ri) -> Spot {
        if (ri == lv.start_room || ri == lv.miner_room) return {-1, 0, -1};
        RoomData& room = lv.rooms[ri];
        const ModelData* m = modelOf(room.model_id);
        if (!m || m->width <= 0) return {-1, 0, -1};
        const int h = (int)m->tiles.size() / m->width;
        if (h != 4 || room.bottom_band) return {-1, 0, -1};    // (a hot room is fine: bands 0/2)
        for (const auto& pt : room.asym_patches) {
            if ((int)pt.size() >= 3 && pt[2] == (int)TileType::LOCKED_DOOR)
                return {-1, 0, -1};
        }
        if (!room.feature_cells.empty()) return {-1, 0, -1};   // phase / hcrunch
        auto air = [&](int band, int f) {
            const int c = f < 10 ? f : 19 - f;
            return m->tiles[band * m->width + c] == (int)TileType::AIR;
        };
        auto bandOf = [&](float y) { return std::min(h - 1, (int)y / (12 / h)); };
        // Prefer the middle of the room: spread the candidates from column 18
        // outwards so the miner is not wedged against an exit.
        for (int d = 0; d < 40; ++d) {
            for (int sgn : {1, -1}) {
                const int dcol = 18 + sgn * d;              // display column
                if (dcol < 3 || dcol > 36) continue;
                const int xpx = dcol * 4;                   // visible left edge
                const int fa = std::min(19, xpx / 8), fb = std::min(19, (xpx + 7) / 8);
                const int mid = std::min(19, (xpx + 3) / 8);
                if (!air(2, fa) || !air(2, fb) || air(3, mid)) continue;
                if (!rr.reach.count({ri, 2, mid})) continue;
                auto clear = [&](int skip) {
                    int cnt = 0;
                    for (int i = 0; i < (int)room.enemies.size(); ++i) {
                        if (i == skip) continue;
                        const EnemyData& e = room.enemies[i];
                        ++cnt;
                        if (bandOf(e.y) == 2
                                || std::abs((int)std::lround(e.x) - dcol) < 3)
                            return false;
                    }
                    for (const LampData& l : room.lamps) {
                        ++cnt;
                        if (bandOf(l.y) == 2
                                || std::abs((int)std::lround(l.x) - dcol) < 3)
                            return false;
                    }
                    return cnt < 2;
                };
                if (clear(-1)) return {ri, dcol, -1};
                for (int i = 0; i < (int)room.enemies.size(); ++i) {
                    const int t = room.enemies[i].type;
                    if (t != (int)EnemyType::BAT && t != (int)EnemyType::SPIDER
                            && t != (int)EnemyType::SNAKE
                            && t != (int)EnemyType::GIANT_MOTH) continue;
                    if (clear(i)) return {ri, dcol, i};
                }
            }
        }
        return {-1, 0, -1};
    };
    // The order the search first visits the rooms spreads the miners out.
    std::vector<int> order;
    for (int ri : rr.order) {
        if (ri != lv.start_room && ri != lv.miner_room) order.push_back(ri);
    }
    // Every room that can host a miner, in route order, with its spot.
    struct Host { int idx; Spot sp; };
    std::vector<Host> hosts;
    for (int i = 0; i < (int)order.size(); ++i) {
        const Spot sp = spotIn(order[i]);
        if (sp.room >= 0) hosts.push_back({i, sp});
    }
    const int n = (int)order.size();
    std::vector<int> pick;                          // indices into hosts
    if (want == 1) {
        int bestCost = 1 << 30;
        for (int i = 0; i < (int)hosts.size(); ++i) {
            const int cost = std::abs(hosts[i].idx - n / 2);
            if (cost < bestCost) { bestCost = cost; pick = {i}; }
        }
    } else {
        int bestCost = 1 << 30;
        for (int i = 0; i < (int)hosts.size(); ++i) {
            for (int j = 0; j < (int)hosts.size(); ++j) {
                if (i == j || (hosts[i].sp.room & 1) == (hosts[j].sp.room & 1)) continue;
                if (hosts[i].idx >= hosts[j].idx) continue;
                const int cost = std::abs(hosts[i].idx - n / 3)
                               + std::abs(hosts[j].idx - 2 * n / 3);
                if (cost < bestCost) { bestCost = cost; pick = {i, j}; }
            }
        }
    }
    if (want == 2 && pick.empty() && !hosts.empty()) {
        pick = {0};                                 // one host: place one miner
    }
    if (pick.empty()) {
        return 0;               // no host room in this level: it keeps its one miner
    }
    int placed = 0;
    for (int hi : pick) {
        const Spot& sp = hosts[hi].sp;
        RoomData& room = lv.rooms[sp.room];
        if (sp.evict >= 0) room.enemies.erase(room.enemies.begin() + sp.evict);
        AddEnemy(room, EnemyType::EXTRA_MINER, (float)sp.col, ExtraMinerY(),
                 0.0f, 0.0f);
        ++placed;
    }
    return placed;
}

// POWER CELLS (user request 2026-10-26): the timer is 120 s, so a level whose
// estimated play time (the route model above) exceeds kCellBudget gets cells on
// its route. Each cell refills the bar once (the kernel latches bit (room
// index & 3) of LevelStartRoom, so cells sit in rooms that differ mod 4) and the
// plan keeps every stretch between refills under kCellBudget, aiming for
// kCellLead after the previous one. Returns the cells placed, or -1 when no
// eligible route cell exists for a stretch (test_generator then fails loudly).
int PlanPowerCells(LevelData& lv, const std::vector<ModelData>& models) {
    const ReachResult rr = AnalyseReach(lv, models);
    if (rr.route.empty() || rr.route.back().cost <= kCellBudget) return 0;
    auto modelOf = [&](int id) -> const ModelData* {
        for (const auto& m : models) {
            if (m.id == id) return &m;
        }
        return nullptr;
    };
    std::set<int> bits;
    for (int i = 0; i < (int)lv.rooms.size(); ++i) {
        for (const EnemyData& e : lv.rooms[i].enemies) {
            if (e.type == (int)EnemyType::POWER_CELL) bits.insert(i & 3);
        }
    }
    // Cells compete with the generator's own objects for the 2 slots per room
    // (from level 9 most route rooms are full): when no free host exists, a
    // plain enemy of a route room is evicted in favour of the cell
    // (evict >= 0 on return). Keys, rafts and tentacles are never evicted.
    // Cells compete with the generator's own objects for the 2 slots per room
    // (from level 9 most route rooms are full): the cell goes on the free air
    // cell NEAREST to the route node (band and column are free: the player walks
    // a few steps to it), and when the room is full a plain enemy is evicted in
    // favour of the cell (evict >= 0 on return). Keys, rafts, tentacles and
    // miners are never evicted.
    int cBand = 0, cCol = 0;
    auto eligible = [&](size_t k, bool replace, int& evict) {
        evict = -1;
        const auto& nd = rr.route[k];
        if (k < 1 || k + 1 >= rr.route.size()) return false;
        if (rr.route[k - 1].room != nd.room || rr.route[k + 1].room != nd.room)
            return false;                   // not a room's arrival/exit cell
        if (nd.room == lv.start_room || nd.room == lv.miner_room) return false;
        if (bits.count(nd.room & 3)) return false;
        RoomData& room = lv.rooms[nd.room];
        const ModelData* m = modelOf(room.model_id);
        if (!m || m->width <= 0) return false;
        const int h = (int)m->tiles.size() / m->width;
        if (h != 4) return false;           // legacy 3-row shapes: skip
        for (const auto& pt : room.asym_patches) {
            if ((int)pt.size() >= 3 && pt[2] == (int)TileType::LOCKED_DOOR)
                return false;               // door rooms allow one non-key enemy
        }
        for (const auto& ft : room.feature_cells) {
            if ((int)ft.size() >= 3 && (ft[2] == (int)TileType::HCRUNCH
                                        || ft[2] == (int)TileType::PHASE))
                return false;               // crunch owns the slot; a phase
                                            // room's row 1 is the gate itself
        }
        auto bandOf = [&](float y) { return std::min(h - 1, (int)y / (12 / h)); };
        // free air cells of the room, nearest to the route node first
        std::vector<std::tuple<int, int, int>> cand;       // (dist, band, col)
        for (const auto& nodeT : rr.reach) {
            const auto [rr_, b, f] = nodeT;
            if (rr_ != nd.room) continue;
            if (m->mid_band_type == 1 && b == 1) continue; // hot band: no objects
            if (room.bottom_band && b == h - 1) continue;  // the water
            cand.push_back({std::abs(b - nd.band) * 4 + std::abs(f - nd.col), b, f});
        }
        std::sort(cand.begin(), cand.end());
        auto clear = [&](int skip, int band, int dcol) {
            int cnt = 0;
            for (int i = 0; i < (int)room.enemies.size(); ++i) {
                if (i == skip) continue;
                const EnemyData& e = room.enemies[i];
                ++cnt;
                if (bandOf(e.y) == band
                        || std::abs((int)std::lround(e.x) - dcol) < 3) return false;
            }
            for (const LampData& l : room.lamps) {
                ++cnt;
                if (bandOf(l.y) == band
                        || std::abs((int)std::lround(l.x) - dcol) < 3) return false;
            }
            return cnt < 2;
        };
        for (const auto& [dist, b, f] : cand) {
            (void)dist;
            if (clear(-1, b, f * 2)) { cBand = b; cCol = f; return true; }
        }
        if (!replace) return false;
        for (const auto& [dist, b, f] : cand) {
            (void)dist;
            for (int i = 0; i < (int)room.enemies.size(); ++i) {
                const int t = room.enemies[i].type;
                if (t != (int)EnemyType::BAT && t != (int)EnemyType::SPIDER
                        && t != (int)EnemyType::SNAKE
                        && t != (int)EnemyType::GIANT_MOTH) continue;
                if (clear(i, b, f * 2)) { evict = i; cBand = b; cCol = f; return true; }
            }
        }
        return false;
    };
    int placed = 0;
    int last = 0;
    const int total = rr.route.back().cost;
    while (total - last > kCellBudget) {
        int pick = -1, pickEvict = -1, ev = -1, pickBand = 0, pickCol = 0;
        // Preference: a free host in the lead window, then a free host anywhere
        // that leaves 10 s of slack, then the same two windows with eviction.
        for (int pass = 0; pass < 4 && pick < 0; ++pass) {
            // pass 0/2: the lead window; 1/3: as late as the budget allows
            const int limit = last + ((pass & 1) ? kCellBudget - 10 * 60 : kCellLead);
            for (size_t k = 0; k < rr.route.size(); ++k) {
                if (rr.route[k].cost <= last) continue;
                if (rr.route[k].cost > limit) break;
                if (eligible(k, pass >= 2, ev)) {
                    pick = (int)k; pickEvict = ev; pickBand = cBand; pickCol = cCol;
                }
            }
        }
        if (pick < 0) {
            return -1;
        }
        const auto& nd = rr.route[pick];
        RoomData& room = lv.rooms[nd.room];
        const ModelData* m = modelOf(room.model_id);
        if (pickEvict >= 0) room.enemies.erase(room.enemies.begin() + pickEvict);
        AddEnemy(room, EnemyType::POWER_CELL, (float)(pickCol * 2),
                 BandY(*m, pickBand), 0.0f, 0.0f);
        bits.insert(nd.room & 3);
        last = nd.cost;
        ++placed;
    }
    return placed;
}

// Moves the room's spider (same band) to the nearest column where the level is
// finishable without crossing a spider zone. Keeps the placement rules the
// generator already enforces: an AIR cell, >= 3 display columns from the other
// objects, off the side-entry edge columns when a neighbour exists. Returns
// false when no column works (the caller then removes the spider).
bool RelocateSpider(LevelData& lv, int ri, const std::vector<ModelData>& models) {
    RoomData& room = lv.rooms[ri];
    const ModelData* sm = nullptr;
    for (const auto& m : models) {
        if (m.id == room.model_id) sm = &m;
    }
    if (!sm || sm->width <= 0) return false;
    int si = -1;
    for (int k = 0; k < (int)room.enemies.size(); ++k) {
        if (room.enemies[k].type == (int)EnemyType::SPIDER) si = k;
    }
    if (si < 0) return false;
    const int bandRows = std::max(1, 12 / std::max(1, sm->height));
    auto bandOf = [&](float y) {
        return std::min(sm->height - 1, std::max(0, (int)y / bandRows));
    };
    const int curBand = bandOf(room.enemies[si].y);
    bool westN = false, eastN = false;
    for (const RoomData& q : lv.rooms) {
        westN = westN || (q.room_x == room.room_x - 1 && q.room_y == room.room_y);
        eastN = eastN || (q.room_x == room.room_x + 1 && q.room_y == room.room_y);
    }
    const int lo = westN ? 2 : 0, hi = eastN ? 17 : 19;
    const int cur = (int)std::lround(room.enemies[si].x);
    // Same band first, then the other walkable bands (never band 0: the
    // arrival band; never a hot middle band: an object there is unkillable).
    std::vector<int> bands{curBand};
    for (int bnd = 1; bnd < sm->height; ++bnd) {
        if (bnd == curBand) continue;
        if (bnd == 1 && sm->mid_band_type == 1) continue;
        bands.push_back(bnd);
    }
    std::vector<int> order;
    for (int d = 0; d < 20; ++d) {
        order.push_back(cur + d);
        if (d) order.push_back(cur - d);
    }
    for (int band : bands) {
        if (band == 0) continue;
        for (int cand : order) {
            if (cand < lo || cand > hi) continue;
            if (cand & 1) continue;   // 8 px sprite = one whole cell (2 columns)
            if (sm->tiles[band * sm->width + cand / 2] != (int)TileType::AIR)
                continue;
            bool clash = false;
            for (int k = 0; k < (int)room.enemies.size(); ++k) {
                if (k == si) continue;
                if (bandOf(room.enemies[k].y) == band
                        || std::abs((int)std::lround(room.enemies[k].x) - cand) < 3)
                    clash = true;
            }
            for (const LampData& l : room.lamps) {
                if (bandOf(l.y) == band
                        || std::abs((int)std::lround(l.x) - cand) < 3)
                    clash = true;
            }
            if (clash) continue;
            const float oldX = room.enemies[si].x, oldY = room.enemies[si].y;
            room.enemies[si].x = (float)cand;
            room.enemies[si].y = BandY(*sm, band);
            const ReachResult rr = AnalyseReach(lv, models);
            if (rr.bombs >= 0 && rr.dangerRooms.empty()) return true;
            room.enemies[si].x = oldX;
            room.enemies[si].y = oldY;
        }
    }
    return false;
}

}  // namespace

// Stage-level LINK check (user rule 2026-10-24). See the header for the rule:
// the runtime exit fires when the player reaches the screen edge and never
// tests the neighbour's wall, so a half-carved link or a band mismatch drops
// him inside a wall on the room change. This mirrors
// tools/convert_level.check_stage_connections (the build gate).
std::vector<std::string> DataSerializer::StageConnectionProblems(
        const std::vector<LevelData>& levels,
        const std::vector<ModelData>& models) {
    std::vector<std::string> out;
    auto findModel = [&](int id) -> const ModelData* {
        for (const auto& m : models) {
            if (m.id == id) return &m;
        }
        return nullptr;
    };
    auto sideBands = [](const ModelData& m) {
        std::vector<int> v;
        for (int band = 1; band <= 2; ++band) {
            if (CellAir(m, band, 0)) v.push_back(band);
        }
        return v;
    };
    int level_n = 0;
    for (const auto& level : levels) {
        ++level_n;
        auto findRoom = [&](int x, int y) -> const RoomData* {
            for (const auto& r : level.rooms) {
                if (r.room_x == x && r.room_y == y) return &r;
            }
            return nullptr;
        };
        for (const auto& room : level.rooms) {
            const ModelData* a = findModel(room.model_id);
            if (!a || a->width <= 0) continue;
            const int bands = (int)a->tiles.size() / a->width;
            if (bands < 3) continue;
            if (const RoomData* east = findRoom(room.room_x + 1, room.room_y)) {
                const ModelData* b = findModel(east->model_id);
                if (!b) continue;
                const std::vector<int> sa = sideBands(*a), sb = sideBands(*b);
                bool shared = false;
                for (int x : sa) {
                    for (int y : sb) {
                        if (x == y) shared = true;
                    }
                }
                if (!sa.empty() && !sb.empty() && !shared) {
                    out.push_back(
                        "level " + std::to_string(level_n) + ": rooms "
                        + std::to_string(room.room_id) + " and "
                        + std::to_string(east->room_id)
                        + " are side by side but open in different bands "
                        "(landing inside a wall)");
                } else if (sa.empty() != sb.empty()) {
                    out.push_back(
                        "level " + std::to_string(level_n) + ": rooms "
                        + std::to_string(room.room_id) + " and "
                        + std::to_string(east->room_id)
                        + " are side by side but only one has a side opening");
                }
            }
            // NO OPENING WITHOUT A NEIGHBOUR (user rule 2026-10-24): the
            // playfield is reflected, so a side link opens BOTH edges and the
            // end room of a horizontal run shows a dead aperture on its far
            // side. It must be plugged with a solid async patch there (ball /
            // M1 cell, indestructible — no bomb reaches an object patch).
            {
                const std::vector<int> open = sideBands(*a);
                if (!open.empty()) {
                    struct Side { const char* name; bool has; int col; int sid; };
                    const Side sides[2] = {
                        {"west", findRoom(room.room_x - 1, room.room_y) != nullptr,
                         0, 1},
                        {"east", findRoom(room.room_x + 1, room.room_y) != nullptr,
                         9, 0},
                    };
                    for (const Side& sd : sides) {
                        if (sd.has) continue;
                        std::vector<int> plugged;
                        for (const auto& pt : room.asym_patches) {
                            // [row, col, tile] defaults to side 0
                            // (right/ball), the 4-element form is explicit.
                            if ((int)pt.size() >= 3 && pt[1] == sd.col
                                    && (pt.size() > 3 ? pt[3] : 0)
                                           == sd.sid) {
                                plugged.push_back(pt[0]);
                            }
                        }
                        for (int band : open) {
                            bool has_plug = false;
                            for (int b : plugged) has_plug = has_plug || b == band;
                            if (has_plug) continue;
                            out.push_back(
                                "level " + std::to_string(level_n) + ": room "
                                + std::to_string(room.room_id)
                                + " has an opening on its " + sd.name
                                + " edge but no room that way and no plug"
                                  " (band " + std::to_string(band) + ")");
                        }
                    }
                }
            }
            if (const RoomData* south = findRoom(room.room_x, room.room_y + 1)) {
                const ModelData* b = findModel(south->model_id);
                if (!b || b->width <= 0) continue;
                if ((int)b->tiles.size() / b->width < 1) continue;
                bool shared = false, any = false;
                for (int x = 0; x < kRoomWidth; ++x) {
                    const bool up = CellAir(*a, bands - 1, x);
                    const bool dn = CellAir(*b, 0, x);
                    any = any || up || dn;
                    shared = shared || (up && dn);
                }
                if (any && !shared) {
                    out.push_back(
                        "level " + std::to_string(level_n) + ": rooms "
                        + std::to_string(room.room_id) + " (above) and "
                        + std::to_string(south->room_id)
                        + " (below) share no open column (landing inside a "
                        "wall)");
                }
            }
        }
    }
    return out;
}


namespace {
// Repair state shared by the outer retry loop and the single build pass it
// drives (see Build20LevelStage): rooms whose archetype is flattened, and what
// the last pass found wrong.
struct StageRepair {
    std::set<std::pair<int, int>> flat;         // (level, room index)
    std::set<std::pair<int, int>> noPatch;      // ledge block dropped there
    std::set<std::pair<int, int>> noSpider;     // spider removed from there
    std::vector<std::pair<int, int>> nextNoSpider;
    std::vector<std::pair<int, int>> nextNoPatch;
    std::set<std::tuple<int, int, int>> chanOff;  // (level, x, y) demoted
    std::vector<std::tuple<int, int, int>> nextChan;
    std::vector<std::pair<int, int>> next;      // rooms to flatten next
    std::vector<std::string> problems;          // unfixable findings
};
StageRepair* g_stageRepair = nullptr;
}  // namespace

void DataSerializer::Build20LevelStage(std::vector<LevelData>& levels,
                                       std::vector<ModelData>& models) {
    if (!g_stageRepair) {
        // OUTER CALL: build, check that every level can be FINISHED, and when
        // one cannot, flatten one more archetype in that level and rebuild
        // (deterministic: no RNG, the repair order is the discovery order).
        // User report 2026-10-25: levels 8, 9, 15 and 18 had no route to the
        // miner at all (the archetypes' centre walls split every reachable
        // room into two mirrored chambers that never join).
        StageRepair rep;
        struct Guard {
            ~Guard() { g_stageRepair = nullptr; g_channelOff = nullptr; }
        } guard;
        g_stageRepair = &rep;
        g_channelOff = &rep.chanOff;
        for (int pass = 0; pass < 400; ++pass) {
            rep.next.clear();
            rep.nextChan.clear();
            rep.nextNoPatch.clear();
            rep.nextNoSpider.clear();
            rep.problems.clear();
            levels.clear();
            models.clear();
            Build20LevelStage(levels, models);
            if (rep.next.empty() && rep.nextChan.empty()
                    && rep.nextNoPatch.empty()
                    && rep.nextNoSpider.empty()) break;
            bool grew = false;
            for (const auto& q : rep.next) grew = rep.flat.insert(q).second || grew;
            for (const auto& q : rep.nextChan)
                grew = rep.chanOff.insert(q).second || grew;
            for (const auto& q : rep.nextNoPatch)
                grew = rep.noPatch.insert(q).second || grew;
            for (const auto& q : rep.nextNoSpider)
                grew = rep.noSpider.insert(q).second || grew;
            if (!grew) break;
        }
        if (!rep.problems.empty()) {
            std::string all;
            for (const auto& pr : rep.problems) all += "\n  " + pr;
            throw std::runtime_error("generated stage cannot be finished:" + all);
        }
        return;
    }
    StageRepair& repair = *g_stageRepair;
    // 1. Every level's walk + the shape mask of each of its rooms. A room's
    //    ROLE (hot / gate / water goal) is part of the shape, so the library
    //    carries hazard variants as well as exit masks. Two passes: the base
    //    library first; if it fits under kShapeBudget the EXTRA archetype
    //    variants are enabled (the generator spends real headroom, never
    //    guesses).
    std::vector<std::vector<GridPos>> walks(kStageLevels);
    std::vector<std::vector<int>> masks(kStageLevels);
    std::vector<std::vector<Role>> roles(kStageLevels);
    std::set<int> used;
    // `variety` = how many ARCHETYPES each room type may use. With the maze
    // layout the exit combinations multiply (7 combos x 2Gap x role bits), so
    // the archetype count is the budget knob: fixed pools wanted 103 shapes,
    // over the 64 the 6-bit shape index allows (measured 2026-10-24).
    auto buildLibrary = [&](bool withExtras, int variety) {
        used.clear();
        for (int l = 1; l <= kStageLevels; ++l) {
            walks[l - 1] = LevelLayout(l, l < 2 ? 2 : l);
            const LevelPlan plan = PlanFor(l);
            const int count = (int)walks[l - 1].size();
            masks[l - 1].clear();
            roles[l - 1].clear();
            // Pass 1: the roles. A hazard needs a room that can HOST it: the
            // maze decides which rooms have a vertical passage, and the three
            // vertical hazards (hot band, phase blink, crunch sweep) need one
            // — a crunch room also cannot host a side link (its band 1 is one
            // solid feature prefix). When the chosen room cannot host, the
            // role MOVES to the first free room that can (user rule 2026-10-24:
            // the layout decides the shapes, so the hazard follows the layout).
            std::vector<bool> vroom(count, false), hroom(count, false);
            std::vector<Role> rl(count, Role::Normal);
            for (int i = 0; i < count; ++i) {
                const GridPos& p = walks[l - 1][i];
                vroom[i] = HasRoomAt(walks[l - 1], p.x, p.y - 1)
                        || HasRoomAt(walks[l - 1], p.x, p.y + 1);
                hroom[i] = HasRoomAt(walks[l - 1], p.x - 1, p.y)
                        || HasRoomAt(walks[l - 1], p.x + 1, p.y);
                rl[i] = RoleForRoom(i, count, plan);
                if (IsChannelRoom(l, walks[l - 1], p)) rl[i] = Role::Normal;
            }
            auto canHost = [&](int i, Role r) {
                if (i <= 0 || i >= count - 1) return false;
                if (r == Role::Hot) return (bool)vroom[i];
                // PHASE (user rule 2026-10-27): a horizontal obstacle only —
                // the player walks/flies across it left<->right, so the room
                // needs a SIDE link. Corridors, L, T and + rooms all qualify
                // (vertical links are fine: the cell has wall above/below).
                if (r == Role::Phase) return (bool)hroom[i];
                // Since 2026-10-24 the kernel prefix starts at pair 1, so a
                // crunch room keeps its side link (the crush gates the way out of
                // the 8-px edge vestibule); it still needs a vertical passage.
                if (r == Role::Hcrunch) {
                    // 2026-10-25: an exit above AND one below (the escape
                    // from band 1 is a >= 2-tile gap on both sides).
                    // and the room under it must take a widened ceiling: not
                    // a channel, not the water goal (see the gap step below).
                    const GridPos& p = walks[l - 1][i];
                    if (FirstEntry(walks[l - 1], i) == 0) return false;
                    if (IsChannelRoom(l, walks[l - 1], p)
                            || !HasRoomAt(walks[l - 1], p.x, p.y - 1)
                            || !HasRoomAt(walks[l - 1], p.x, p.y + 1)) {
                        return false;
                    }
                    for (int j = 0; j < count; ++j) {
                        const GridPos& q = walks[l - 1][j];
                        if (q.x != p.x || q.y != p.y + 1) continue;
                        return j != count - 1
                            && !IsChannelRoom(l, walks[l - 1], q);
                    }
                    return false;
                }
                return true;
            };
            // Most RESTRICTIVE first: the crunch needs a vertical-only room
            // (its band 1 is one solid feature prefix, so it cannot host a
            // side link), while hot/phase only need a vertical one. On a dense
            // level the stem room is usually the only vertical-only room, so
            // the crunch claims it and hot moves elsewhere.
            for (const Role want : {Role::Hcrunch, Role::Hot, Role::Phase}) {
                for (int i = 1; i < count - 1; ++i) {
                    if (rl[i] != want || canHost(i, want)) continue;
                    int host = -1;
                    for (int j = 1; j < count - 1 && host < 0; ++j) {
                        if (j != i && rl[j] == Role::Normal && canHost(j, want)) {
                            host = j;
                        }
                    }
                    if (host < 0) {
                        // No free host: STEAL one from a less restrictive role
                        // (hot/phase) that has somewhere else to go.
                        for (int j = 1; j < count - 1 && host < 0; ++j) {
                            if (j == i || !canHost(j, want)) continue;
                            if (rl[j] == Role::Normal) {
                                host = j;
                                break;
                            }
                            if (rl[j] != Role::Hot && rl[j] != Role::Phase) {
                                continue;
                            }
                            bool moved = false;
                            for (int k = 1; k < count - 1; ++k) {
                                if (k == i || k == j) continue;
                                if (rl[k] == Role::Normal && canHost(k, rl[j])) {
                                    rl[k] = rl[j];
                                    moved = true;
                                    break;
                                }
                            }
                            // The crunch is the rarest hazard (it needs a
                            // vertical-only room): if the victim cannot be
                            // rehoused, it is dropped and the crunch takes the
                            // host anyway.
                            rl[j] = Role::Normal;
                            host = j;
                            (void)moved;
                        }
                    }
                    if (host < 0) {
                        rl[i] = Role::Normal;   // nowhere to host it: drop it
                        continue;
                    }
                    rl[i] = Role::Normal;
                    rl[host] = want;
                }
            }
            // Pass 2: the shape mask (arch keyed by the room's role + the exit
            // combination; corridor rooms stay plain, see below).
            for (int i = 0; i < count; ++i) {
                const Role role = rl[i];
                roles[l - 1].push_back(role);
                const GridPos& here = walks[l - 1][i];
                const bool verticalRoom = vroom[i];
                int arch = 0;
                if (verticalRoom
                        && !IsChannelRoom(l, walks[l - 1], here)) {
                    if (role == Role::Hot) {
                        const int* pool;
                        int n;
                        if (l > 10) {
                            pool = withExtras ? kHotExtra : kHotLate;
                            n = withExtras ? 6 : 4;
                        } else {
                            pool = kHotBase;
                            n = 3;
                        }
                        if (n > variety) n = variety;
                        arch = pool[l % n];
                    } else if (i == 0 && l >= 8) {
                        // The START room drops the player in at cell 4, so its
                        // band 1 MUST keep that column open: arch 14 is
                        // HotDrop, the only start archetype with the drop
                        // column carved.
                        arch = 14;
                    } else if (role == Role::Normal && i > 0
                               && i < count - 1) {
                        const int* pool = withExtras ? kNormalExtra
                                                     : kNormalBase;
                        int n = withExtras ? 7 : 5;
                        if (n > variety) n = variety;
                        arch = pool[(l + i) % n];
                    }
                }
                if (repair.flat.count({l, i})) arch = 0;   // reach repair
                const int mask = RoomShapeMask(l, walks[l - 1], walks[l - 1][i],
                                               i, role, plan.twogap)
                                 | (arch << kArchShift);
                masks[l - 1].push_back(mask);
            }
            for (const int m : masks[l - 1]) used.insert(m);
        }
    };
    // Widest archetype set that fits the budget, then the richer archetypes
    // if they also fit; otherwise keep the base library.
    for (int variety = 3; variety >= 1; --variety) {
        buildLibrary(false, variety);
        if ((int)used.size() <= kShapeBudget) break;
    }
    {
        const std::vector<std::vector<int>> baseMasks = masks;
        const std::vector<std::vector<Role>> baseRoles = roles;
        const std::set<int> baseUsed = used;
        buildLibrary(true, 3);
        if ((int)used.size() > kShapeBudget) {
            masks = baseMasks;
            roles = baseRoles;
            used = baseUsed;
        }
    }

    // --- VERTICAL APERTURE PAIRING (user report 2026-10-24, "stuck_002") ----
    // The player keeps his X through a vertical link (ExitEdgeTab drops him at
    // RoomY 0 with the same RoomX), so every column the room ABOVE can fall
    // through MUST be open in the room BELOW's ceiling. The library has two
    // vertical flavors — plain cells 8/9 (kVertExitA/B) and the 2-gap cells
    // 3/6 (kGapA/B) — and a mixed pair drops him through a hole that is a
    // solid cell below: StepDown then refuses for as long as he stands there,
    // so he hangs at the top of the new screen until he walks out of it.
    // Cure a broken pair by giving the room ABOVE the 2-gap flavor (its floor
    // becomes {3,6}, which both ceilings contain), else the room BELOW.
    // Water/channel floors are open 1..9 and are skipped: CheckBandTouch kills
    // him in the strip (RoomY >= 115) before a down exit can happen.
    {
        auto vertCells = [](int mask, bool ceiling) {
            // MakeShapeModel applies the 4-row expansion (the plan is 3 rows,
            // band 2 is derived), so the FLOOR is the model's LAST row, not
            // kGenRows-1 = the derived band 2 (which is open across the whole
            // route and made every pair look broken).
            const ModelData m = MakeShapeModel(0, mask);
            const int rows = (int)m.tiles.size() / kRoomWidth;
            const int base = ceiling ? 0 : (rows - 1) * kRoomWidth;
            std::set<int> air;
            for (int x = 0; x < kRoomWidth; ++x) {
                if (m.tiles[base + x] == (int)TileType::AIR) air.insert(x);
            }
            return air;
        };
        // Adding the 2-gap flavor to one room changes BOTH of its rows, so a
        // pair fixed here can break the pair below it: re-scan until stable.
        for (int pass = 0; pass < 8; ++pass) {
            bool changed = false;
            for (int l = 1; l <= kStageLevels; ++l) {
                const auto& wk = walks[l - 1];
                std::map<std::pair<int, int>, int> at;
                for (int i = 0; i < (int)wk.size(); ++i) {
                    at[{wk[i].x, wk[i].y}] = i;
                }
                for (int i = 0; i < (int)wk.size(); ++i) {
                    const auto it = at.find({wk[i].x, wk[i].y + 1});
                    if (it == at.end()) continue;
                    const int j = it->second;
                    int& above = masks[l - 1][i];
                    int& below = masks[l - 1][j];
                    if (above & (SHAPE_WATER | SHAPE_CHANNEL)) continue;
                    if (!(below & SHAPE_N)) continue;   // no ceiling opening
                    auto paired = [&]() {
                        const std::set<int> up = vertCells(above, false);
                        const std::set<int> dn = vertCells(below, true);
                        for (int c : up) {
                            if (!dn.count(c)) return false;
                        }
                        return true;
                    };
                    if (paired()) continue;
                    above |= SHAPE_2GAP;
                    changed = true;
                    if (!paired()) below |= SHAPE_2GAP;
                    if (!paired()) {
                        // The ceiling is NARROW (SHAPE_N1 opens cell 3 only, e.g.
                        // a channel room): match it by narrowing the floor.
                        above |= SHAPE_S1;
                        changed = true;
                        // ...unless that turns the room into a STRAIGHT DROP
                        // (ceiling == floor, which the plan forbids): widen the
                        // ceiling to the 2-gap flavor instead of leaving a
                        // shaft the player falls through without steering.
                        const std::set<int> top = vertCells(above, true);
                        if (top == vertCells(above, false) && top.size() == 1) {
                            above &= ~SHAPE_N1;
                            above |= SHAPE_2GAP;
                        }
                    }
                    if (!paired()) {
                        const std::set<int> up = vertCells(above, false);
                        const std::set<int> dn = vertCells(below, true);
                        std::string u, d;
                        for (int c : up) u += std::to_string(c);
                        for (int c : dn) d += std::to_string(c);
                        throw std::runtime_error(
                                "level " + std::to_string(l) + ": rooms "
                                + std::to_string(i) + " and "
                                + std::to_string(j) + " are stacked but the "
                                "upper floor {" + u + "} is not open in the "
                                "lower ceiling {" + d + "} (masks "
                                + std::to_string(above) + "/"
                                + std::to_string(below) + ") — the player "
                                "would land inside a wall");
                    }
                }
            }
            if (!changed) break;
        }
        // HCRUNCH GAPS (user rule 2026-10-25): the player survives a crunch
        // only by leaving band 1, so its ceiling AND floor need a contiguous
        // gap of >= 4 tiles (user rule 2026-10-26: `###....###`, a 1-2 cell
        // gap is a death trap). Every shape under 4 gets the widened cells 3..6,
        // and the room below a widened floor widens its ceiling to match.
        // Channel / water neighbours cannot take the widening: the crunch
        // is dropped there (the room stays an ordinary one).
        auto longestRun = [](const std::set<int>& air) {
            int best = 0, run = 0;
            for (int x = 0; x < kRoomWidth; ++x) {
                run = air.count(x) ? run + 1 : 0;
                best = std::max(best, run);
            }
            return best;
        };
        const std::vector<std::vector<int>> plainMasks = masks;
        std::vector<std::pair<int, int>> crunchRooms;   // (level, room)
        for (int l = 1; l <= kStageLevels; ++l) {
            for (int i = 1; i + 1 < (int)walks[l - 1].size(); ++i) {
                if (roles[l - 1][i] == Role::Hcrunch) {
                    crunchRooms.push_back({l, i});
                }
            }
        }
        auto widen = [&](int l, int i) {
            const auto& wk = walks[l - 1];
            int& m = masks[l - 1][i];
            int below = -1;
            for (int j = 0; j < (int)wk.size(); ++j) {
                if (wk[j].x == wk[i].x && wk[j].y == wk[i].y + 1) below = j;
            }
            // Band 3 crunch (entered from above): its ceiling is the middle
            // band (always open on a crunch room: no archetype) and its floor
            // is the cave floor, so only the floor gap can be short.
            const bool bandThree = FirstEntry(wk, i) == 1;
            if (!bandThree && longestRun(vertCells(m, true)) < 4) m |= SHAPE_WN;
            // The band-2 crunch's floor is band 3 (row index 2),
            // NOT the cave floor (band 4) that vertCells(.., false) reads —
            // that mix-up let a 2-cell gap through (levels 17/19, 2026-10-27).
            const ModelData built = MakeShapeModel(0, m);
            std::set<int> lowAir;
            for (int x = 0; x < kRoomWidth; ++x) {
                if (built.tiles[2 * kRoomWidth + x] == (int)TileType::AIR) {
                    lowAir.insert(x);
                }
            }
            const bool floorShort = longestRun(vertCells(m, false)) < 4;
            if (floorShort || (!bandThree && longestRun(lowAir) < 4)) {
                m |= SHAPE_WS;
                if (floorShort && below >= 0) {
                    // An ordinary room under the widened floor drops its
                    // archetype: a plain ceiling-widened shape is shared by
                    // every such neighbour instead of costing a shape each.
                    if (roles[l - 1][below] == Role::Normal
                            && !(masks[l - 1][below] & SHAPE_START)) {
                        masks[l - 1][below] &= ~(kArchMask << kArchShift);
                    }
                    masks[l - 1][below] |= SHAPE_WN;
                }
            }
        };
        // Every widened room (and the one under it) is a NEW shape; the bank3
        // shape window holds only so many, so the LAST crunch rooms go back to
        // ordinary rooms until the library fits kCrunchShapeCap.
        auto liveShapes = [&]() {
            std::set<int> live;
            for (const auto& row : masks) for (int m : row) live.insert(m);
            return (int)live.size();
        };
        // Keep order: the FIRST crunch of each level, then the extra ones, so
        // the capacity trim never leaves a level without its crunch.
        {
            std::vector<std::pair<int, int>> first, extra;
            std::set<int> seen;
            for (const auto& c : crunchRooms) {
                (seen.insert(c.first).second ? first : extra).push_back(c);
            }
            crunchRooms = first;
            crunchRooms.insert(crunchRooms.end(), extra.begin(), extra.end());
        }
        size_t kept = crunchRooms.size();
        for (const auto& c : crunchRooms) widen(c.first, c.second);
        while (kept > 0 && liveShapes() > kCrunchShapeCap) {
            --kept;
            masks = plainMasks;
            for (size_t k = 0; k < kept; ++k) {
                widen(crunchRooms[k].first, crunchRooms[k].second);
            }
            const auto& c = crunchRooms[kept];
            roles[c.first - 1][c.second] = Role::Normal;
        }
        // The pass REWRITES masks, so a pre-pass value that no room uses any
        // more is an orphan MODEL (15 of them after the first run): drop it —
        // model ids must stay contiguous with LEVEL_SHAPE_COUNT.
        std::set<int> live;
        for (const auto& row : masks) {
            for (int m : row) live.insert(m);
        }
        for (auto it = used.begin(); it != used.end();) {
            it = live.count(*it) ? std::next(it) : used.erase(it);
        }
        for (int m : live) used.insert(m);   // the post-pass masks themselves
    }

    // 2. The shape library: model ids ARE the ascending masks (deterministic).
    models.clear();
    std::map<int, int> shapeId;
    for (int mask : used) {
        shapeId[mask] = (int)models.size();
        models.push_back(MakeShapeModel(shapeId[mask], mask));
    }

    // 3. The levels, in play order.
    levels.clear();
    levels.reserve(kStageLevels);
    // COMPLETABILITY GUARD: refuse to emit a stage whose rooms cannot be
    // crossed (construction opens the corridor, but a future edit could break
    // it; the editor and the CLI both surface this as a hard error).
    for (const ModelData& m : models) {
        const std::string problem = RoomConnectivityProblem(m);
        if (!problem.empty()) {
            throw std::runtime_error("generated room '" + m.name + "' is "
                                     "impassable: " + problem);
        }
    }

    for (int l = 1; l <= kStageLevels; ++l) {
        LevelData level;
        level.level_id = l;
        level.name = "Level " + std::to_string(l);
        level.wall_r = kLevelPalettes[l - 1][0];
        level.wall_g = kLevelPalettes[l - 1][1];
        level.wall_b = kLevelPalettes[l - 1][2];
        level.wall2_r = Lift(level.wall_r);
        level.wall2_g = Lift(level.wall_g);
        level.wall2_b = Lift(level.wall_b);
        level.start_room = 0;                 // convert: 0 is the kernel constant
        const int roomCount = (int)walks[l - 1].size();
        level.miner_room = roomCount - 1;     // the goal is the last room
        level.miner_x = kMinerX;              // on the water-goal rock
        // User rule 2026-10-21: if the walk enters the goal room from a SIDE,
        // the miner waits on the OPPOSITE side (on the entry side the room is
        // trivial). Vertical entry keeps the left-positioned miner.
        if (roomCount >= 2) {
            const GridPos& goalPos = walks[l - 1][roomCount - 1];
            const GridPos& prevPos = walks[l - 1][roomCount - 2];
            if (prevPos.x != goalPos.x) {
                level.miner_x = (prevPos.x < goalPos.x) ? kMinerFarX
                                                        : kMinerX;
            }
        }
        // Miner Y = the goal rock top - 12 px: 84 px (7 rows) on a 3-band room,
        // 96 px (8 rows) on a 4-band one (the floor band sits 36 px lower).
        // Every water-goal shape is a non-gate shape, so it is 4-row.
        level.miner_y = 8.0f;
        level.miner_dir = 1;
        const LevelPlan plan = PlanFor(l);
        for (int i = 0; i < roomCount; ++i) {
            RoomData room;
            room.room_id = i;
            room.model_id = shapeId[masks[l - 1][i]];
            room.room_x = walks[l - 1][i].x;
            room.room_y = walks[l - 1][i].y;
            if (roles[l - 1][i] == Role::Gate) {
                // LOCKED_DOOR cells ON THE CORRIDOR (left/M1 side), one per
                // corridor cell (2 max = the patch cap). Solid until the
                // level's key is held, then touch opens the room's door.
                const int doorCol = (masks[l - 1][i] & SHAPE_2GAP)
                                        ? kGapA : kVertExitA;
                room.asym_patches.push_back(
                    {1, doorCol, (int)TileType::LOCKED_DOOR, 1});
            }
            if (roles[l - 1][i] == Role::Phase) {
                // The corridor blinks: 45 frames solid, 45 open. The cell sits
                // on band 2 of a straight corridor room with WALL above and
                // below it (cell 2: the floor holes are cells 4/5/8/9), so it
                // is only ever crossed sideways (user rule 2026-10-27).
                room.feature_cells.push_back(
                    {1, kPhaseCell, (int)TileType::PHASE});
            }
            if (roles[l - 1][i] == Role::Hcrunch) {
                // Fixed 10-cell prefix on the middle band (live stage form).
                // Band 3 (row 2) when he arrives falling from above, band 2
                // (row 1) when he arrives climbing from below.
                const int crow = FirstEntry(walks[l - 1], i) == 1 ? 2 : 1;
                for (int c = 0; c < kRoomWidth; ++c) {
                    room.feature_cells.push_back(
                        {crow, c, (int)TileType::HCRUNCH});
                }
            }
            // Advanced hot rooms (> level 10): a solid async block sits in
            // the gap the player must use — bomb it (thin cell) or take the
            // longer gap (usefull_hot_walls_004). The M1 column needs walls
            // in bands 0/2, so scan for a legal cell near the gap.
            // Start rooms never take a hot gap block: their drop column must
            // stay open (HotDrop), and they carry their own async rule below.
            if (roles[l - 1][i] == Role::Hot && l > 10 && i != 0
                    && !repair.noPatch.count({l, i})) {
                const ModelData& sm = models[shapeId[masks[l - 1][i]]];
                const int hidx = ((masks[l - 1][i] >> kArchShift) & kArchMask) - 8;
                const int gapCell = kArchHotGapX[hidx] / 2;
                for (int c = gapCell; c <= gapCell + 1; ++c) {
                    if (c < 1 || c > 7) continue;
                    if (sm.tiles[1 * kRoomWidth + c] == 0
                            && sm.tiles[0 * kRoomWidth + c] != 0
                            && sm.tiles[2 * kRoomWidth + c] != 0
                            && (sm.height <= 3
                                || sm.tiles[3 * kRoomWidth + c] != 0)) {
                        room.asym_patches.push_back(
                            {1, c, (int)TileType::SOLID_WALL, 1});
                        break;
                    }
                }
            }
            // Start room: an async block beside the exit gap from level 7
            // (user rule 2026-10-21: first room has no enemies, but async in
            // the path is welcome). Cell 7 + its mirror cell 2 are open in
            // every start shape (row 1 is '#.........').
            if (i == 0 && plan.patch && l >= 7 && !repair.noPatch.count({l, 0})) {
                // M1 guard: the patch cell must be OPEN in band 1 and WALLED in
                // bands 0/2 (the whole-cave strip paints/hides the column).
                // Prefer col 7 (next to the exit gap); hot archetypes may fill
                // it, so fall back to 1.
                const ModelData& sm0 = models[shapeId[masks[l - 1][i]]];
                for (int c : {7, 6, 5, 4, 3, 2, 1}) {
                    if (sm0.tiles[1 * kRoomWidth + c] == 0
                            && sm0.tiles[0 * kRoomWidth + c] != 0
                            && sm0.tiles[2 * kRoomWidth + c] != 0
                            && (sm0.height <= 3
                                || sm0.tiles[3 * kRoomWidth + c] != 0)) {
                        room.asym_patches.push_back(
                            {1, c, (int)TileType::SOLID_WALL, 1});
                        break;
                    }
                }
            }
            // Async BLOCKS: a plain solid patch (not a special) sprinkled
            // through ordinary rooms so async rides WITH enemies. The gate/
            // phase/hcrunch rooms keep their own special alone; the start and
            // goal rooms stay clean (spawn/pickup).
            //
            // M1 (side 1) is the primary: the whole-cave latch needs the
            // patched band OPEN and the other two bands WALLED at that column.
            // The optional second block is the BALL (side 0, additive) on the
            // mirrored cell — it only needs band 1 open there.
            if (roles[l - 1][i] == Role::Normal && i > 0
                    && i < roomCount - 1 && plan.patch && i % 3 == 2
                    && !repair.noPatch.count({l, i})) {
                const ModelData& sm = models[shapeId[masks[l - 1][i]]];
                int col = -1;
                for (int c = 1; c <= 7; ++c) {
                    // The M1 strip paints ONE column across the WHOLE cave, so
                    // every band the patch does not paint must be walled there
                    // — band 3 included now that the floor is its own band
                    // (2026-10-24; the converter hard-fails otherwise).
                    if (sm.tiles[1 * kRoomWidth + c] == 0
                            && sm.tiles[0 * kRoomWidth + c] != 0
                            && sm.tiles[2 * kRoomWidth + c] != 0
                            && (sm.height <= 3
                                || sm.tiles[3 * kRoomWidth + c] != 0)) {
                        col = c;
                        break;
                    }
                }
                if (col >= 0) {
                    room.asym_patches.push_back(
                        {1, col, (int)TileType::SOLID_WALL, 1});
                    if (plan.patch2) {
                        const int other = kRoomWidth - 1 - col;
                        if (sm.tiles[1 * kRoomWidth + other] == 0) {
                            room.asym_patches.push_back(
                                {1, other, (int)TileType::SOLID_WALL, 0});
                        }
                    }
                }
            }
            // PLUG the dead side (user rule 2026-10-24, screenshot
            // layout_invalid_exists.png): the playfield is REFLECTED, so a side
            // link opens BOTH edges — a room with a single horizontal neighbour
            // shows a hole on its far side. M1 (left) / ball (right) paint an
            // 8-px cell there; both are OBJECTS, not PF, so no bomb can remove
            // them (indestructible by construction — no new kernel code).
            //
            // The plug owns only the DEAD side's object: an async block on the
            // other side survives, and a block that sat on the plugged side is
            // re-homed to the opposite object (the same mirrored pair the block
            // emitter above uses). Without this every edge room — half the
            // stage — would silently lose its async content.
            {
                const GridPos& p = walks[l - 1][i];
                const bool west = HasRoomAt(walks[l - 1], p.x - 1, p.y);
                const bool east = HasRoomAt(walks[l - 1], p.x + 1, p.y);
                if (west != east) {
                    const ModelData& sm = models[shapeId[masks[l - 1][i]]];
                    const int dead_side = west ? 0 : 1;   // 0 = right/ball
                    const int dead_col = west ? 9 : 0;
                    auto side_of = [](const std::vector<int>& pt) {
                        return (int)pt.size() > 3 ? pt[3] : 0;
                    };
                    // Keep the other side's patches, remember what the plug
                    // displaced so it can be re-homed.
                    std::vector<std::vector<int>> kept;
                    std::vector<int> displaced;   // column of a dropped block
                    for (const auto& pt : room.asym_patches) {
                        if (side_of(pt) == dead_side) {
                            if ((int)pt.size() >= 3 && pt[0] == 1)
                                displaced.push_back(pt[1]);
                            continue;
                        }
                        kept.push_back(pt);
                    }
                    room.asym_patches = kept;
                    // Only the bands where the shape really carries the
                    // aperture get a plug: the wall-hide guard requires the
                    // patched cell to be OPEN (a wall would hide the patch).
                    for (int band = kHorizExitA;
                         band <= std::min(kHorizExitB, sm.height - 2); ++band) {
                        if (sm.tiles[band * sm.width] != (int)TileType::AIR)
                            continue;
                        room.asym_patches.push_back(
                            {band, dead_col, (int)TileType::SOLID_WALL,
                             dead_side});
                    }
                    // Re-home the displaced async block on the free object.
                    if (!displaced.empty()
                            && (int)room.asym_patches.size() < 2) {
                        const int other = kRoomWidth - 1 - displaced.front();
                        if (dead_side == 1) {
                            // M1 was plugged → the BALL takes the block; it
                            // only needs its own band-1 cell open.
                            if (sm.tiles[1 * kRoomWidth + other] == 0)
                                room.asym_patches.push_back(
                                    {1, other, (int)TileType::SOLID_WALL, 0});
                        } else {
                            // BALL was plugged → the M1 takes the block; the
                            // whole-cave latch needs the other bands walled.
                            if (sm.tiles[1 * kRoomWidth + other] == 0
                                    && sm.tiles[0 * kRoomWidth + other] != 0
                                    && sm.tiles[2 * kRoomWidth + other] != 0
                                    && (sm.height <= 3
                                        || sm.tiles[3 * kRoomWidth + other] != 0))
                                room.asym_patches.push_back(
                                    {1, other, (int)TileType::SOLID_WALL, 1});
                        }
                    }
                }
            }
            if (masks[l - 1][i] & SHAPE_CHANNEL) {
                // Water crossing: raft on the open water + one bat in the
                // centre shaft (cell 8). No role objects (the hot ceiling is
                // the challenge).
                room.bottom_band = true;
                room.bottom_r = 24;
                room.bottom_g = 88;
                room.bottom_b = 208;
                {
                    const int rc = RaftCell(models[shapeId[masks[l - 1][i]]]);
                    if (rc >= 0)
                        AddEnemy(room, EnemyType::RAFT, (float)(rc * 2), kRaftY,
                                 1.0f, 0.0f);
                }
                const int chBat = NearestAir(models[shapeId[masks[l - 1][i]]],
                                             0, 8);
                if (chBat >= 0) {
                    AddEnemy(room, EnemyType::BAT, (float)(chBat * 2),
                         BandY(models[shapeId[masks[l - 1][i]]], 0),
                             1.25f + 0.25f * (l % 4), 13.0f);
                }
            } else {
                const bool keyHost = (i + 1 < roomCount
                                      && roles[l - 1][i + 1] == Role::Gate);
                const int roomArch = (masks[l - 1][i] >> kArchShift) & kArchMask;
                const ModelData& roomShape = models[shapeId[masks[l - 1][i]]];
                FillRoomObjects(l, i, roomCount, roles[l - 1][i], plan, room,
                                roomShape, keyHost, roomArch);
            }
            // Two objects on the SAME display column blink vertically between
            // their bands (ONE GRP1, 30 Hz rotation) and read as "I can barely
            // see anything" until one dies (user report 2026-10-24: level 5
            // room 2, two enemies at column 16 in bands 0 and 3). Nudge the
            // later object at least 3 display columns away, onto an air cell of
            // its own band; if no such cell exists, leave the pair alone.
            {
                const ModelData& sm = models[shapeId[masks[l - 1][i]]];
                const int rowsPerBand = std::max(1, 12 / std::max(1, sm.height));
                // Stay on the LEFT half: display col 0..19 (the playfield is
                // mirrored, and convert/tests map a column with col/2).
                auto airAt = [&](int band, int dcol) {
                    if (dcol < 0 || dcol > 19) return false;
                    const int cell = dcol / 2;
                    return band >= 0 && band < sm.height
                        && sm.tiles[band * sm.width + cell]
                               == (int)TileType::AIR;
                };
                for (size_t b = 1; b < room.enemies.size(); ++b) {
                    const int cb = (int)std::lround(room.enemies[b].x);
                    const int bandB = (int)room.enemies[b].y / rowsPerBand;
                    bool clash = false;
                    for (size_t a = 0; a < b; ++a) {
                        if (std::abs((int)std::lround(room.enemies[a].x) - cb) < 3)
                            clash = true;
                    }
                    if (!clash) continue;
                    // A spider keeps to whole cells (even column): start at 4.
                    const bool spiderB = room.enemies[b].type == (int)EnemyType::SPIDER;
                    for (int d = spiderB ? 4 : 3; d <= 9 && clash; d += 2) {
                        for (int sign : {1, -1}) {
                            const int cand = cb + sign * d;
                            if (airAt(bandB, cand)) {
                                room.enemies[b].x = (float)cand;
                                clash = false;
                                break;
                            }
                        }
                    }
                }
            }
            level.rooms.push_back(room);
        }
        // Keys: one per gate, placed in the nearest earlier room that is not
        // another gate and has a free row (row 2 first). Row = y/4.
        for (int i = 1; i < roomCount; ++i) {
            if (roles[l - 1][i] != Role::Gate) continue;
            // Host search: PREFER middle rooms (the start room is the clean
            // spawn — no enemies/items unless there is no other host).
            bool keyPlaced = false;
            for (int j = i - 1; j >= 1 && !keyPlaced; --j) {
                if (roles[l - 1][j] == Role::Gate) continue;
                if (roles[l - 1][j] == Role::Hcrunch) continue;  // no objects
                if (ObjectCount(level.rooms[j]) >= 2) continue;
                // Free cells the shape actually has open: row 1 cell 5 (x 10)
                // on normal/hot shapes, else the exit corridor (cell 8, x 16).
                const ModelData& kShape = models[shapeId[masks[l - 1][j]]];
                int kband = 1, kprefer = 5;
                float ky = 5.0f;
                if (RowOccupied(level.rooms[j], 1)) {
                    if (!RowOccupied(level.rooms[j], 0)) {
                        kband = 0; kprefer = 8; ky = BandY(kShape, 0);
                    } else if (!RowOccupied(level.rooms[j],
                                            FloorBand(kShape))) {
                        kband = FloorBand(kShape); kprefer = 8;
                        ky = BandY(kShape, kband);
                    } else {
                        continue;
                    }
                }
                const int kcell = NearestAir(kShape, kband, kprefer);
                if (kcell < 0) continue;
                AddEnemy(level.rooms[j], EnemyType::KEY, (float)(kcell * 2),
                         ky, 1.0f, 0.0f);
                keyPlaced = true;
            }
            if (!keyPlaced && ObjectCount(level.rooms[0]) < 2
                    && !RowOccupied(level.rooms[0], 1)) {
                const int kcell = NearestAir(
                    models[shapeId[masks[l - 1][0]]], 1, 5);
                if (kcell >= 0) {
                    AddEnemy(level.rooms[0], EnemyType::KEY,
                             (float)(kcell * 2), 5.0f, 1.0f, 0.0f);
                }
            }
        }
        // Two-gap route choice (user rule 2026-10-20): one of the two
        // ceiling gaps carries a lamp (even rooms) or a spider (odd rooms),
        // the other stays empty — dropping blind is the risk. Runs AFTER the
        // keys so a gate's host room keeps its free slot; gate/hcrunch rooms
        // are skipped (door rule / no objects).
        if (plan.twogap) {
            for (int i = 1; i < roomCount - 1; ++i) {
                if (roles[l - 1][i] == Role::Hcrunch
                        || roles[l - 1][i] == Role::Gate
                        || roles[l - 1][i] == Role::Phase) continue;
                RoomData& room = level.rooms[i];
                if (ObjectCount(room) >= 2 || RowOccupied(room, 0)) continue;
                const int gap = (i % 2) ? kGapB : kGapA;
                const ModelData& gShape = models[shapeId[masks[l - 1][i]]];
                if (i % 2 || i >= 8) {   // lamps only where the dark mask works
                    const int gcell = NearestAir(gShape, 0, gap);
                    if (gcell < 0) continue;
                    AddEnemy(room, EnemyType::SPIDER, (float)(gcell * 2),
                             BandY(gShape, 0), 1.0f + 0.25f * (l % 4),
                             8.0f);
                } else {
                    const int gcell = LampCell(gShape, 0, gap);
                    if (gcell < 0) continue;
                    LampData lamp;
                    lamp.x = (float)(gcell * 2);
                    lamp.y = BandY(gShape, 0);
                    lamp.lit = true;
                    room.lamps.push_back(lamp);
                }
            }
        }
        // NO INSTANT DEATH ON ARRIVAL (user report 2026-10-24, level 6 room 2:
        // "on the next screen he stops falling"). A vertical link drops the
        // player at the band-0 aperture columns with NO input yet, so an enemy
        // sitting there overlaps his box the frame the room loads and
        // CheckEnemyHit takes a life before he can move; the respawn hover then
        // holds him at the top. Runs AFTER the keys and the two-gap hazard so it
        // sees every object. Only BAND 0 is instant: from band 1 on he has
        // landed and can react — the two-gap "drop blind is the risk" hazard
        // survives, one band lower. Lamps are collectibles, harmless to touch.
        // SIDE links are the same class (guard only, the live stage has none
        // today): entering from a neighbour keeps the player's Y, so an enemy
        // standing in a side-aperture band on the entry edge column kills him
        // the frame the room loads.
        std::set<std::pair<int, int>> occupied;
        for (const RoomData& q : level.rooms) {
            occupied.insert({q.room_x, q.room_y});
        }
        for (int j = 0; j < (int)level.rooms.size(); ++j) {
            RoomData& room = level.rooms[j];
            const ModelData& sm = models[shapeId[masks[l - 1][j]]];
            const int rowsPerBand = std::max(1, 12 / std::max(1, sm.height));
            auto airAt = [&](int band, int dcol) {
                if (dcol < 0 || dcol > 19) return false;
                const int cell = dcol / 2;
                return band >= 0 && band < sm.height
                    && sm.tiles[band * sm.width + cell]
                           == (int)TileType::AIR;
            };
            std::vector<int> aper;
            for (int x = 0; x < sm.width; ++x) {
                if (sm.tiles[x] == (int)TileType::AIR) {   // band 0 = entry
                    aper.push_back(2 * x);
                    aper.push_back(2 * x + 1);
                }
            }
            const bool westNbr = occupied.count({room.room_x - 1, room.room_y});
            const bool eastNbr = occupied.count({room.room_x + 1, room.room_y});
            std::set<int> sideBands;      // walkable bands open on col 0
            for (int b = 1; b + 1 < sm.height; ++b) {
                if (sm.tiles[b * sm.width] == (int)TileType::AIR) {
                    sideBands.insert(b);
                }
            }
            auto dangerous = [&](int band, int col) -> bool {
                if (band == 0) {                  // vertical arrival
                    for (int c : aper) {
                        if (std::abs(col - c) <= 1) return true;
                    }
                    return false;
                }
                if (!sideBands.count(band)) return false;
                return (westNbr && col <= 1) || (eastNbr && col >= 18);
            };
            std::set<int> taken;   // the editor's 1-object-per-row cap
            for (const EnemyData& q : room.enemies) taken.insert((int)q.y / 4);
            for (const LampData& q : room.lamps) taken.insert((int)q.y / 4);
            for (size_t k = 0; k < room.enemies.size();) {
                EnemyData& e = room.enemies[k];
                const int eband = (int)e.y / rowsPerBand;
                if (e.type == (int)EnemyType::RAFT
                        || !dangerous(eband, (int)std::lround(e.x))) {
                    ++k;
                    continue;
                }
                const int col = (int)std::lround(e.x);
                bool placed = false;
                const bool gated = roles[l - 1][j] == Role::Gate
                                   || roles[l - 1][j] == Role::Phase;
                for (int nb : {1, 2, 3}) {
                    if (nb >= sm.height) continue;
                    // Gate/phase rooms: band 1 holds the gate and band 2 stays
                    // empty (user ruling 2026-10-26) - floor band or nothing.
                    if (gated && nb != FloorBand(sm)) continue;
                    // A hot middle band is a hazard wall: an object parked in
                    // it is invisible and unkillable (the generator's own rule).
                    if (nb == 1 && sm.mid_band_type == 1) continue;
                    if (taken.count((int)BandY(sm, nb) / 4)) continue;
                    // A spider keeps to whole cells (even column): start at 4.
                    for (int d = e.type == (int)EnemyType::SPIDER ? 4 : 3;
                         d <= 15 && !placed; d += 2) {
                        for (int sign : {1, -1}) {
                            const int cand = col + sign * d;
                            if (!airAt(nb, cand) || dangerous(nb, cand)) {
                                continue;
                            }
                            e.x = (float)cand;
                            e.y = BandY(sm, nb);
                            taken.insert((int)e.y / 4);
                            placed = true;
                            break;
                        }
                    }
                    if (placed) break;
                }
                if (placed) {
                    ++k;
                    continue;
                }
                room.enemies.erase(room.enemies.begin() + (long)k);
            }
        }
        // ---- FINAL OBJECT SEPARATION (user rule 2026-10-25) ----------------
        // ONE GRP1 cannot draw two objects on the same scanlines: StageSlot1
        // (bank2) pairs slot 1 only when the two objects sit in DIFFERENT
        // bands, so a same-band pair falls back to the 30 Hz rotation and both
        // blink. Two objects in different bands can still end up in one band
        // as soon as either moves (moth/bat/snake patrol rows within a band),
        // and a shared display column looks like one flickering sprite.
        // User report: level 5 room 2, both enemies at column 19 -> "lots of
        // flicker". The nudge in the room loop runs BEFORE the keys, the lamps
        // and the arrival fix-ups, so it cannot see the final content: this
        // pass runs last, and convert_level.check_object_bands mirrors it.
        for (int j = 0; j < (int)level.rooms.size(); ++j) {
            RoomData& room = level.rooms[j];
            const ModelData& sm = models[shapeId[masks[l - 1][j]]];
            const int rowsPerBand = std::max(1, 12 / std::max(1, sm.height));
            auto bandOf = [&](float y) {
                return std::min(sm.height - 1,
                                std::max(0, (int)y / rowsPerBand));
            };
            auto bandRow = [&](int band) {
                return (float)(band * rowsPerBand + rowsPerBand / 2);
            };
            auto airAt = [&](int band, int dcol) {   // left half: 0..19
                if (dcol < 0 || dcol > 19) return false;
                const int cell = dcol / 2;
                return band >= 0 && band < sm.height
                    && sm.tiles[band * sm.width + cell]
                           == (int)TileType::AIR;
            };
            auto colOf = [&](float x) { return (int)std::lround(x); };
            auto clashes = [&](int band, int col, int skipEnemy,
                               int skipLamp) {
                for (int a = 0; a < (int)room.enemies.size(); ++a) {
                    if (a == skipEnemy) continue;
                    if (bandOf(room.enemies[a].y) == band
                        || std::abs(colOf(room.enemies[a].x) - col) < 3)
                        return true;
                }
                for (int a = 0; a < (int)room.lamps.size(); ++a) {
                    if (a == skipLamp) continue;
                    if (bandOf(room.lamps[a].y) == band
                        || std::abs(colOf(room.lamps[a].x) - col) < 3)
                        return true;
                }
                return false;
            };
            // BAND 0 IS THE ARRIVAL BAND: the vertical/side arrival pass
            // above owns it, and an object there kills the player on contact
            // the frame the room loads. Never move anything INTO it, and keep
            // clear of the side-entry edge columns when a neighbour exists.
            const bool westN = occupied.count({room.room_x - 1,
                                               room.room_y}) > 0;
            const bool eastN = occupied.count({room.room_x + 1,
                                               room.room_y}) > 0;
            const int colLo = westN ? 2 : 0;
            const int colHi = eastN ? 17 : 19;
            for (int b = 0; b < (int)room.enemies.size(); ++b) {
                // The raft is placed on purpose (under the drop shaft, on the
                // water surface): it never moves - its partner does. This pass
                // used to drag it to the first air column (user 2026-10-28:
                // level 11 room 8 / level 14 room 9, raft beside the shaft).
                if (room.enemies[b].type == (int)EnemyType::RAFT) continue;
                const int bandB = bandOf(room.enemies[b].y);
                if (!clashes(bandB, colOf(room.enemies[b].x), b, -1)) continue;
                bool fixed = false;
                for (int band = 1; band < sm.height && !fixed; ++band) {
                    if (band == 1 && sm.mid_band_type == 1) continue;
                    for (int dcol = colLo; dcol <= colHi && !fixed; ++dcol) {
                        if (!airAt(band, dcol)) continue;
                        if ((dcol & 1) && room.enemies[b].type == (int)EnemyType::SPIDER)
                            continue;   // whole cells only
                        if (clashes(band, dcol, b, -1)) continue;
                        room.enemies[b].x = (float)dcol;
                        room.enemies[b].y = bandRow(band);
                        fixed = true;
                    }
                }
                // Nothing legal left: one object beats a blinking pair (the
                // build gate rejects a same-band room).
                if (!fixed) room.enemies.erase(room.enemies.begin() + b--);
            }
            for (int b = 0; b < (int)room.lamps.size(); ++b) {
                const int bandB = bandOf(room.lamps[b].y);
                if (!clashes(bandB, colOf(room.lamps[b].x), -1, b)) continue;
                for (int band = 1; band < sm.height; ++band) {
                    if (band == 1 && sm.mid_band_type == 1) continue;
                    bool done = false;
                    for (int dcol = colLo; dcol <= colHi && !done; ++dcol) {
                        if (!airAt(band, dcol)) continue;
                        if (clashes(band, dcol, -1, b)) continue;
                        room.lamps[b].y = bandRow(band);
                        done = true;
                    }
                    if (done) break;
                }
            }
        }
        // WHOLE CELLS (user report 2026-10-28, enemy_inside_wall.png, level 14
        // room 8: a bat on column 13 straddled cells 6 and 7 and was drawn half
        // inside the wall): an enemy sprite is 8 px = one cell, and a column is
        // 4 px, so an ODD column straddles two cells while only cell x/2 was
        // ever checked for air. Every enemy except the snake (it lives in its
        // wall by design), the raft and the extra miner sits on an EVEN column.
        // Flooring keeps the validated cell; when that lands within 3 columns of
        // another object, the next even column is used if it is air too.
        for (int j = 0; j < (int)level.rooms.size(); ++j) {
            RoomData& room = level.rooms[j];
            const ModelData& sm = models[shapeId[masks[l - 1][j]]];
            const int rowsPerBand = std::max(1, 12 / std::max(1, sm.height));
            for (size_t k = 0; k < room.enemies.size(); ++k) {
                EnemyData& e = room.enemies[k];
                if (e.type == (int)EnemyType::SNAKE
                        || e.type == (int)EnemyType::RAFT
                        || e.type == (int)EnemyType::KEY) continue;
                const int col = (int)std::lround(e.x);
                if (!(col & 1)) continue;
                auto near = [&](int c) {
                    for (size_t o = 0; o < room.enemies.size(); ++o) {
                        if (o != k && std::abs((int)std::lround(
                                room.enemies[o].x) - c) < 3) return true;
                    }
                    for (const LampData& m : room.lamps) {
                        if (std::abs((int)std::lround(m.x) - c) < 3) return true;
                    }
                    return false;
                };
                const int band = std::min(sm.height - 1,
                                          std::max(0, (int)e.y / rowsPerBand));
                auto airEven = [&](int c) {
                    return c >= 0 && c <= 18 && !(c & 1)
                        && sm.tiles[band * sm.width + c / 2]
                               == (int)TileType::AIR;
                };
                int pick = col - 1;          // same cell as before: always air
                for (int d = 1; d <= 15 && near(pick); d += 2) {
                    for (int sign : {-1, 1}) {
                        const int cand = col + sign * d;
                        if (airEven(cand) && !near(cand)) { pick = cand; break; }
                    }
                }
                e.x = (float)pick;
            }
        }
        // SPIDER direction (user 2026-10-28): dir right = sweeps DOWN first,
        // left = UP first. Near the cave bottom/top the direction is forced so
        // the 24 px sweep never leaves the screen; elsewhere the generator's
        // pick stays. (AddEnemy sets it too; y may have moved since.)
        for (int j = 0; j < (int)level.rooms.size(); ++j) {
            const ModelData& sm = models[shapeId[masks[l - 1][j]]];
            for (EnemyData& e : level.rooms[j].enemies) {
                int f = 0;
                if (e.type == (int)EnemyType::SPIDER)
                    f = SpiderForcedDirIn(sm, e.y, (int)std::lround(e.x));
                else if (e.type == (int)EnemyType::GIANT_MOTH)
                    f = MothForcedDirIn(sm, e.y, (int)std::lround(e.x));
                else
                    continue;
                if (f != 0) e.dir = f;      // walls and cave edges, both ways
            }
        }
        levels.push_back(level);
    }

    // N=4 (2026-10-24): the PLANS are built in 3 rows (0 ceiling / 1 shaft /
    // 2 floor) and MakeShapeModel emits 4 bands, band 2 being the vertical
    // route's continuation. Gate/phase shapes stay 3-row (their door cell IS
    // the corridor, so band 2 has to stay open for the descent and the strip
    // cannot be patched twice) and the converter/editor pad those on load.

    // FINISHABILITY (user report 2026-10-25). Every level must reach the miner
    // with at most kMaxBombsPerLevel bombs. A failing level asks the outer loop
    // to flatten the archetype of the nearest room that still has one (a plain
    // shape keeps its band 1 open from the shaft to the seam); a hot room is
    // never flattened (its hot pattern is the arch itself).
    for (const auto& q : repair.noSpider) {
        auto& es = levels[q.first - 1].rooms[q.second].enemies;
        es.erase(std::remove_if(es.begin(), es.end(), [](const EnemyData& e) {
                     return e.type == (int)EnemyType::SPIDER;
                 }), es.end());
    }
    for (int l = 1; l <= kStageLevels; ++l) {
        // A spider the route has to pass: slide it to a clear column first
        // (content stays), remove it only when no column works.
        for (int tries = 0; tries < 16; ++tries) {
            const ReachResult pre = AnalyseReach(levels[l - 1], models);
            if (pre.dangerRooms.empty()) break;
            if (!RelocateSpider(levels[l - 1], pre.dangerRooms.front(), models))
                break;
        }
        const ReachResult rr = AnalyseReach(levels[l - 1], models);
        // Still crossing one: remove that spider (the room keeps its other
        // object). Checked first - the blocks and the chambers below are
        // judged on the route that remains.
        {
            bool dq = false;
            for (int ri : rr.dangerRooms) {
                if (repair.noSpider.count({l, ri})) continue;
                repair.nextNoSpider.push_back({l, ri});
                dq = true;
                break;
            }
            if (dq) continue;
        }
        // A strip nobody can bomb (see AnalyseReach) is a pointless wall, and in the
        // start room it can trap the player in the arrival chamber (user report
        // 2026-10-26, level 18): drop it and rebuild the level without it.
        {
            bool dropped = false;
            for (int ri : rr.deadStrips) {
                if (repair.noPatch.count({l, ri})) continue;
                repair.nextNoPatch.push_back({l, ri});
                dropped = true;
            }
            if (dropped) continue;
        }
        bool onlyStartBlock = true;     // the one block a route may cross
        for (int ri : rr.crossed) onlyStartBlock = onlyStartBlock && ri == 0;
        if (rr.bombs >= 0 && rr.bombs <= kMaxBombsPerLevel && onlyStartBlock)
            continue;
        bool queued = false;
        if (rr.bombs > 0) {
            // Reachable only through ledge blocks (a level may ask for the
            // START room's designed block and nothing else): drop the ledge
            // block of a room on that route.
            for (int ri : rr.crossed) {
                if (ri == 0 || repair.noPatch.count({l, ri})) continue;
                repair.nextNoPatch.push_back({l, ri});
                queued = true;
                break;
            }
        }
        if (queued) continue;
        for (int ri : rr.order) {
            const int arch = (masks[l - 1][ri] >> kArchShift) & kArchMask;
            if (arch == 0 || roles[l - 1][ri] == Role::Hot) continue;
            if (repair.flat.count({l, ri})) continue;
            repair.next.push_back({l, ri});
            queued = true;
            break;
        }
        if (!queued) {
            // Nothing left to flatten: a CHANNEL room (hot ceiling, water
            // floor) is only crossable from a vertical shaft, and the side
            // exit is walled off from the water - demote the first one.
            for (int i = 0; i < (int)walks[l - 1].size() && !queued; ++i) {
                if (!(masks[l - 1][i] & SHAPE_CHANNEL)) continue;
                repair.nextChan.push_back(
                    {l, walks[l - 1][i].x, walks[l - 1][i].y});
                queued = true;
            }
        }
        if (!queued) {
            repair.problems.push_back(
                "level " + std::to_string(l) + ": "
                + (rr.bombs < 0 ? std::string("the miner is unreachable")
                                : "the miner needs " + std::to_string(rr.bombs)
                                  + " bombs")
                + " and no room is left to flatten");
        }
    }

    // Extra miners next, then the power cells: the cells' route has to include
    // the miners the player must walk to.
    for (int l = 1; l <= kStageLevels; ++l) {
        if (PlaceExtraMiners(levels[l - 1], models, l) < 0) {
            repair.problems.push_back(
                "level " + std::to_string(l) + ": no room can host its extra "
                "miner(s)");
        }
    }
    // Power cells go in LAST: the route they sit on is the finished level's.
    for (int l = 1; l <= kStageLevels; ++l) {
        if (PlanPowerCells(levels[l - 1], models) < 0) {
            repair.problems.push_back(
                "level " + std::to_string(l) + ": the route is longer than the "
                "timer but no room can host a power cell");
        }
    }
}

// ---------------------------------------------------------------------------
// Authentic stage import: converts pixel-decoded maps of the original
// Activision H.E.R.O. levels (source: atariage.com HEROMaps by Adam Lewis)
// into standard LevelData JSON files.
// ---------------------------------------------------------------------------
namespace {

struct AuthEntity {
    int col = 0;
    int row = 0;
    int n = 0;
    std::string kind;
    template <class Archive>
    void serialize(Archive& ar) {
        ar(CEREAL_NVP(col), CEREAL_NVP(row), CEREAL_NVP(n), CEREAL_NVP(kind));
    }
};

struct AuthRoom {
    std::vector<std::string> grid;
    std::vector<AuthEntity> entities;
    template <class Archive>
    void serialize(Archive& ar) {
        ar(CEREAL_NVP(grid), CEREAL_NVP(entities));
    }
};

struct AuthLevel {
    int id = 0;
    std::vector<AuthRoom> rooms;
    template <class Archive>
    void serialize(Archive& ar) {
        ar(CEREAL_NVP(id), CEREAL_NVP(rooms));
    }
};

struct AuthFile {
    std::vector<AuthLevel> levels;
    template <class Archive>
    void serialize(Archive& ar) {
        ar(CEREAL_NVP(levels));
    }
};

// Maps a 16-wide engine column onto the 19-wide source map column
static int SrcCol(int c) {
    int s = (int)(((c + 0.5f) * 19.0f / 16.0f) - 0.5f);
    return std::max(0, std::min(18, s));
}

static bool Passable(char ch) { return ch != '#' && ch != 'M' && ch != 'F'; }

} // namespace

bool DataSerializer::ImportAuthenticMaps(const std::string& intermediateJsonPath, const std::string& outputDirectory) {
    // Check if levels already exist in output directory (avoid overwriting user-edited levels)
    for (int i = 1; i <= 20; ++i) {
        std::string filename = outputDirectory + "/level_" + (i < 10 ? "0" : "") + std::to_string(i) + ".json";
        if (!std::filesystem::exists(filename)) {
            // At least one level missing, proceed with import
            goto import_levels;
        }
    }
    // All 20 levels already exist, skip import - user has edited levels
    return true;

import_levels:
    try {
        std::ifstream is(intermediateJsonPath);
        if (!is.is_open()) return false;

        AuthFile file;
        try {
            cereal::JSONInputArchive archive(is);
            archive(cereal::make_nvp("levels", file.levels));
        } catch (const std::exception&) {
            return false;
        }
        if (file.levels.empty()) return false;

        std::filesystem::create_directories(outputDirectory);

        // Collect all models across all levels into a global models vector
        std::vector<ModelData> allModels;
        int nextModelId = 0;

        for (const auto& srcLevel : file.levels) {
            if (srcLevel.id < 1 || srcLevel.id > 20 || srcLevel.rooms.empty()) continue;

            LevelData lvl;
            lvl.level_id = srcLevel.id;
            lvl.name = "Level " + std::to_string(srcLevel.id);
            lvl.wall_r = kLevelPalettes[srcLevel.id - 1][0];
            lvl.wall_g = kLevelPalettes[srcLevel.id - 1][1];
            lvl.wall_b = kLevelPalettes[srcLevel.id - 1][2];
            lvl.start_room = 0;

            // Temporary vector for this level's models (for connectivity checks)
            std::vector<ModelData> levelModels;
            int roomIdx = 0;
            for (const auto& srcRoom : srcLevel.rooms) {
                if ((int)srcRoom.grid.size() < 12) continue;

                // Create model for this room
                ModelData model;
                model.name = "Level " + std::to_string(srcLevel.id) + " Room " + std::to_string(roomIdx + 1);
                model.width = 16;
                model.height = 12;
                model.tiles.assign(16 * 12, (int)TileType::AIR);

                // Decode structure with 19 -> 16 column compression
                static const std::map<char, int> charToTile = {
                    {'#', (int)TileType::SOLID_WALL},
                    {'F', (int)TileType::FRAGILE_WALL},
                    {'M', (int)TileType::REINFORCED_WALL},
                    {'~', (int)TileType::LAVA},
                };

                for (int y = 0; y < 12; ++y) {
                    const std::string& srcLine = srcRoom.grid[y];
                    for (int x = 0; x < 16; ++x) {
                        char ch = SrcCol(x) < (int)srcLine.size() ? srcLine[SrcCol(x)] : '.';
                        auto it = charToTile.find(ch);
                        if (it != charToTile.end()) {
                            model.tiles[y * 16 + x] = it->second;
                        }
                    }
                }

                // Solid borders with preserved shaft openings from the map
                auto borderIsOpen = [&](int y, int x) {
                    if (y == 0) return Passable(srcRoom.grid[0][SrcCol(x)]) && Passable(srcRoom.grid[1][SrcCol(x)]) && Passable(srcRoom.grid[2][SrcCol(x)]);
                    if (y == 11) return Passable(srcRoom.grid[11][SrcCol(x)]) && Passable(srcRoom.grid[10][SrcCol(x)]) && Passable(srcRoom.grid[9][SrcCol(x)]);
                    if (x == 0) return Passable(srcRoom.grid[y][0]) && Passable(srcRoom.grid[y][1]) && Passable(srcRoom.grid[y][2]);
                    if (x == 15) return Passable(srcRoom.grid[y][18]) && Passable(srcRoom.grid[y][17]) && Passable(srcRoom.grid[y][16]);
                    return false;
                };
                for (int x = 0; x < 16; ++x) {
                    model.tiles[x] = borderIsOpen(0, x) ? (int)TileType::AIR : (int)TileType::SOLID_WALL;
                    model.tiles[11 * 16 + x] = borderIsOpen(11, x) ? (int)TileType::AIR : (int)TileType::SOLID_WALL;
                }
                for (int y = 1; y < 11; ++y) {
                    model.tiles[y * 16] = borderIsOpen(y, 0) ? (int)TileType::AIR : (int)TileType::SOLID_WALL;
                    model.tiles[y * 16 + 15] = borderIsOpen(y, 15) ? (int)TileType::AIR : (int)TileType::SOLID_WALL;
                }

                // Guard against degenerate hollow bands
                int solids = 0;
                for (int t : model.tiles) {
                    if (t == (int)TileType::SOLID_WALL) solids++;
                }
                if (solids < 30) {
                    for (int y = 1; y < 11; ++y) {
                        model.tiles[y * 16] = (int)TileType::SOLID_WALL;
                        model.tiles[y * 16 + 15] = (int)TileType::SOLID_WALL;
                    }
                    int cx = 7 + (roomIdx % 2);
                    model.tiles[cx] = (int)TileType::AIR;
                    model.tiles[11 * 16 + cx] = (int)TileType::AIR;
                }

                // Connectivity: stacked rooms must link vertically
                if (roomIdx > 0 && !levelModels.empty()) {
                    auto& prevModel = levelModels.back();
                    std::vector<int> prevOpen;
                    for (int x = 0; x < 16; ++x) {
                        if (prevModel.tiles[11 * 16 + x] == (int)TileType::AIR) prevOpen.push_back(x);
                    }
                    bool linked = false;
                    for (int x : prevOpen) {
                        if (model.tiles[x] == (int)TileType::AIR) linked = true;
                    }
                    if (!linked) {
                        if (!prevOpen.empty()) {
                            for (int x : prevOpen) model.tiles[x] = (int)TileType::AIR;
                        } else {
                            for (int x = 7; x <= 8; ++x) {
                                prevModel.tiles[11 * 16 + x] = (int)TileType::AIR;
                                model.tiles[x] = (int)TileType::AIR;
                            }
                        }
                    }
                }

                model.id = nextModelId;
                levelModels.push_back(model);
                allModels.push_back(model);

                // Create room referencing this model
                RoomData room;
                room.room_id = roomIdx;
                room.model_id = nextModelId;
                room.room_x = 0;
                room.room_y = roomIdx;
                nextModelId++;

                // Entities detected in the map art
                int enemyCount = 0;
                for (const auto& ent : srcRoom.entities) {
                    float ex = (float)ent.col + 0.5f;
                    float ey = (float)ent.row + 0.4f;

                    if (roomIdx == 0 && ent.kind == "H") {
                        continue;
                    }

                    EnemyData ed;
                    bool isEnemy = true;
                    switch (ent.kind[0]) {
                        case 'v': ed.type = (int)hero::EnemyType::SNAKE; break;
                        case 's': ed.type = (int)hero::EnemyType::SPIDER; break;
                        case 'P': ed.type = (int)hero::EnemyType::BAT; break;
                        default: isEnemy = false; break;
                    }

                    if (isEnemy && enemyCount < 3 && ent.row >= 2 && ent.row <= 10) {
                        if (roomIdx == (int)srcLevel.rooms.size() - 1 && ent.row >= 6 &&
                            (ed.type == (int)hero::EnemyType::SNAKE || ed.type == (int)hero::EnemyType::BAT) &&
                            ent.col >= 10) {
                            lvl.miner_room = roomIdx;
                            lvl.miner_x = ex;
                            lvl.miner_y = ey;
                            isEnemy = false;
                        }
                    } else {
                        isEnemy = false;
                    }

                    if (isEnemy) {
                        ed.x = ex;
                        ed.y = ey;
                        ed.range_min = std::max(0.0f, ex - 3.0f);
                        ed.range_max = std::min(15.0f, ex + 3.0f);
                        ed.speed = 1.0f + (srcLevel.id % 5) * 0.15f;
                        ed.dir = (enemyCount % 2 == 0) ? 1 : -1;
                        room.enemies.push_back(ed);
                        enemyCount++;
                    } else if (ent.kind == "L") {
                        LampData lamp;
                        lamp.x = ex;
                        lamp.y = (float)ent.row + 0.5f;
                        lamp.lit = true;
                        room.lamps.push_back(lamp);
                    }
                }

                lvl.rooms.push_back(room);
                roomIdx++;
            }

            // Defaults if detection missed the miner
            if (lvl.miner_room == 0 && lvl.rooms.size() > 1) {
                lvl.miner_room = (int)lvl.rooms.size() - 1;
                lvl.miner_x = 13.0f;
                lvl.miner_y = 9.9f;
            }

            std::string filename = outputDirectory + "/level_" +
                                   (srcLevel.id < 10 ? "0" : "") + std::to_string(srcLevel.id) + ".json";
            SaveLevelToFile(lvl, filename);
            std::cout << "Imported authentic stage " << srcLevel.id << " (" << lvl.rooms.size() << " rooms)" << std::endl;
        }

        // Save all models to models/models.json
        std::string modelsDir = outputDirectory + "/models";
        std::filesystem::create_directories(modelsDir);
        SaveModelsToFile(allModels, modelsDir + "/models.json");

        return true;
    } catch (const std::exception& e) {
        std::cerr << "ImportAuthenticMaps failed: " << e.what() << std::endl;
        return false;
    }
}

} // namespace hero
