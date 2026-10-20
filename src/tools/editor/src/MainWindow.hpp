/*
 * Savior AI - Level Editor
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

#include <QMainWindow>
#include <QComboBox>
#include <QLabel>
#include <QPushButton>
#include <QCheckBox>
#include <QListWidget>
#include <QSettings>
#include <QDir>
#include <QAction>
#include <QTabWidget>
#include <vector>

#include "MapCanvas.hpp"
#include "UndoHistory.hpp"
#include "LevelData.hpp"

namespace editor {

enum class EditMode {
    MODEL_EDIT,
    LEVEL_EDIT
};

class MainWindow : public QMainWindow {
    Q_OBJECT

public:
    explicit MainWindow(QWidget* parent = nullptr);
    ~MainWindow();

private slots:
    void NewLevel();
    void OpenLevel();
    void SaveLevel();
    void SaveLevelAs();
    // 2026-10-20 (user): ONE stage file (models + all 20 levels) is the only
    // project shape. The editor loads <gameDataDir>/stage.json at start
    // (importing legacy level_*.json into memory if that is all it finds) and
    // Save/Generate always write that one path — no dialogs.
    void LoadDefaultStage();
    void SaveStage();
    // E2 (2026-10-20): build the deterministic 20-level (210-room) stage,
    // replace the current one and save it immediately.
    void GenerateLevelStage();
    void SelectGameDataDir();
    void PerformUndo();

    void AddRoomAbove();
    void AddRoomBelow();
    void AddRoomLeft();
    void AddRoomRight();
    void RemoveRoom();

    void OnRoomChanged(int index);
    void OnStageSelected(int index);
    void OnModelSelected(int index);
    void OnMidBandChanged(int index);
    void PickWallColor();
    void PickWallColor2();
    void PickBandColor();
    void OnBottomBandToggled(bool checked);

    void OnLevelModified();
    void OnMouseMovedToTile(int tileX, int tileY);
    void OnFacingChanged(int dir);
    void ToggleInitialFacing();
    void OnTabChanged(int index);

    void AddModel();
    void RemoveModel();
    void OnModelAssignmentChanged(int modelIdx);

private:
    void SetupUI();
    void InitGameDataDir();
    void LoadModels();
    void SaveModels();
    void PopulateStageCombo();
    void PopulateRoomCombo();
    void PopulateModelCombo();
    void UpdateUIFromLevel();
    void UpdateRoomDirectionButtons();
    void SwitchEditMode(EditMode mode);
    void RefreshToolList();

    void CreateRoomInDirection(int dirX, int dirY);
    bool RoomExistsAt(int rx, int ry) const;

    // Unified stage file (E1 2026-10-20): the current level is a slot of
    // m_stageLevels; SaveStage writes models + every level to m_stageFilePath.
    bool SyncCurrentLevelToStage();
    void EnterStageMode(const std::string& path);

    QIcon MakeToolIcon(BrushTool tool) const;
    void RefreshToolIcons();

    void PushUndoState();
    void ResetUndoStack();
    bool IsModified() const { return m_history.IsModified(); }
    void UpdateWindowTitleAndUndoState();

    hero::LevelData m_levelData;
    std::vector<hero::ModelData> m_models; // global models shared across levels
    QString m_currentFilePath;
    QString m_modelsFilePath;
    QString m_gameDataDir;
    // Unified stage mode (E1): when set, the combo lists the stage's levels and
    // saves write the ONE stage file (models included) — never models.json.
    QString m_stageFilePath;
    bool m_stageMode = false;
    int m_stageLevelIndex = -1;
    std::vector<hero::LevelData> m_stageLevels;
    bool m_ignoreComboEvents = false;
    EditMode m_editMode = EditMode::MODEL_EDIT;

    // Undo System
    UndoHistory<hero::LevelData> m_history;
    QAction* m_undoAction = nullptr;

    MapCanvas* m_canvas = nullptr;

    QComboBox* m_stageCombo = nullptr;
    QComboBox* m_roomCombo = nullptr;
    QPushButton* m_colorBtn = nullptr;
    QPushButton* m_colorBtn2 = nullptr;
    QCheckBox* m_bottomBandCheck = nullptr;
    QPushButton* m_bandColorBtn = nullptr;

    // Directional Room Buttons
    QPushButton* m_addUpBtn = nullptr;
    QPushButton* m_addDownBtn = nullptr;
    QPushButton* m_addLeftBtn = nullptr;
    QPushButton* m_addRightBtn = nullptr;

    // Tab widgets
    QTabWidget* m_tabWidget = nullptr;

    // Model tab widgets
    QListWidget* m_modelList = nullptr;
    QListWidget* m_modelToolList = nullptr;
    QComboBox* m_midBandCombo = nullptr;

    // Level tab widgets
    QComboBox* m_modelAssignCombo = nullptr;
    QListWidget* m_levelToolList = nullptr;
    QPushButton* m_facingBtn = nullptr;
};

} // namespace editor
