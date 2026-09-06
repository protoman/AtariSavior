/*
 * Savior SDL - H.E.R.O. Atari 2600 Remake
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
    static void GenerateAll20DefaultLevels(const std::string& outputDirectory);
    // Converts the pixel-decoded authentic H.E.R.O. stage maps into standard
    // level JSON files. Returns false if the intermediate file is missing.
    static bool ImportAuthenticMaps(const std::string& intermediateJsonPath, const std::string& outputDirectory);
};

} // namespace hero
