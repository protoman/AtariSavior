/*
 * Savior AI - Atari 2600 Remake
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

#pragma once

#include "LevelData.hpp"
#include <string>

namespace hero {

class DataSerializer {
public:
    static bool SaveLevelToFile(const LevelData& level, const std::string& filepath);
    static bool LoadLevelFromFile(LevelData& level, const std::string& filepath);
    static bool SaveModelsToFile(const std::vector<ModelData>& models, const std::string& filepath);
    static bool LoadModelsFromFile(std::vector<ModelData>& models, const std::string& filepath);
    // Unified stage file (E1 2026-10-20): models + every level in one json.
    // Save always writes the canonical `{"stage": {...}}` form; Load accepts
    // both that and the bare `{"models": ..., "levels": ...}` form, and keeps
    // the levels in file order (the converter's play order / LevelDataTable).
    static bool SaveStageToFile(const std::vector<LevelData>& levels,
                                const std::vector<ModelData>& models,
                                const std::string& filepath);
    static bool LoadStageFromFile(std::vector<LevelData>& levels,
                                  std::vector<ModelData>& models,
                                  const std::string& filepath);
    // 2026-10-17 format change: async walls moved from the MODEL to the ROOM
    // (RoomData::asym_patches / feature_cells) so a model SHAPE can be reused
    // by rooms with different async. This migrates a legacy project in place:
    // every level_*.json in `levelsDir` gets its models' async copied into the
    // rooms that reference them (a model's P/V/C grid tiles become the room's
    // feature_cells + SOLID_WALL, which is the same PF byte), then the model
    // fields are cleared and models.json is rewritten. Idempotent: a project
    // already migrated reports `false` and nothing is written.
    // Returns true when at least one file changed.
    static bool MigrateAsyncToRooms(std::vector<ModelData>& models,
                                    const std::string& levelsDir,
                                    const std::string& modelsPath);
    // E2 (2026-10-20): the 20-level stage. Level n has n rooms (1..20 = 210
    // rooms) built from a SHARED SHAPE LIBRARY keyed by the carved exit set, so
    // 210 rooms cost a handful of model shapes (see the layout notes at the
    // implementation). Deterministic by construction: no RNG, no clock — two
    // calls produce identical data, so two saved files are byte-identical.
    // Build only: the caller decides where the file goes (the editor never
    // writes a stage path on its own).
    static void Build20LevelStage(std::vector<LevelData>& levels,
                                  std::vector<ModelData>& models);
    // Converts the pixel-decoded authentic H.E.R.O. stage maps into standard
    // level JSON files. Returns false if the intermediate file is missing.
    static bool ImportAuthenticMaps(const std::string& intermediateJsonPath, const std::string& outputDirectory);
};

} // namespace hero
