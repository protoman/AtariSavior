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
    int withPatches = 0;
    for (const auto& m : original) {
        if (!m.asym_patches.empty()) ++withPatches;
    }
    if (fileHasPatches && withPatches == 0) {
        std::fprintf(stderr,
                     "selftest: file contains asym_patches but the LOADER "
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
    }
    std::printf("selftest OK: %zu models, %d with asym_patches, "
                "save->load round-trip clean\n",
                original.size(), withPatches);
    return 0;
}

int main(int argc, char* argv[]) {
    if (argc == 3 && std::string(argv[1]) == "--selftest") {
        return RunSelfTest(argv[2]);
    }
    QApplication app(argc, argv);
    app.setApplicationName("Savior AI Level Editor");
    app.setOrganizationName("SaviorAI");

    editor::MainWindow window;
    window.show();

    return app.exec();
}
