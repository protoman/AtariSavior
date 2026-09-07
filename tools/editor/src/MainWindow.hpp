/*
 * Savior SDL - H.E.R.O. Level Editor
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
#include <QSpinBox>
#include <QLineEdit>
#include <QLabel>
#include <QPushButton>
#include <QListWidget>
#include <QSettings>
#include <QDir>
#include <QAction>
#include <vector>

#include "MapCanvas.hpp"
#include "UndoHistory.hpp"
#include "LevelData.hpp"

namespace editor {

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
    void SelectGameDataDir();
    void PerformUndo();

    void AddRoomAbove();
    void AddRoomBelow();
    void AddRoomLeft();
    void AddRoomRight();
    void RemoveRoom();

    void OnRoomChanged(int index);
    void OnStageSelected(int index);
    void PickWallColor();
    void PickWallColor2();

    void OnLevelModified();
    void OnMouseMovedToTile(int tileX, int tileY);

private:
    void SetupUI();
    void InitGameDataDir();
    void PopulateStageCombo();
    void PopulateRoomCombo();
    void UpdateUIFromLevel();
    void UpdateRoomDirectionButtons();

    void CreateRoomInDirection(int dirX, int dirY);
    bool RoomExistsAt(int rx, int ry) const;
    bool HasExitInDirection(int roomIndex, int dirX, int dirY) const;

    QIcon MakeToolIcon(BrushTool tool) const;
    void RefreshToolIcons();

    void PushUndoState();
    void ResetUndoStack();
    bool IsModified() const { return m_history.IsModified(); }
    void UpdateWindowTitleAndUndoState();

    hero::LevelData m_levelData;
    QString m_currentFilePath;
    QString m_gameDataDir;
    bool m_ignoreComboEvents = false;

    // Undo System
    UndoHistory<hero::LevelData> m_history;
    QAction* m_undoAction = nullptr;

    MapCanvas* m_canvas = nullptr;

    QComboBox* m_stageCombo = nullptr;
    QSpinBox* m_levelIdSpin = nullptr;
    QLineEdit* m_levelNameEdit = nullptr;
    QComboBox* m_roomCombo = nullptr;
    QPushButton* m_colorBtn = nullptr;
    QPushButton* m_colorBtn2 = nullptr;

    // Directional Room Buttons
    QPushButton* m_addUpBtn = nullptr;
    QPushButton* m_addDownBtn = nullptr;
    QPushButton* m_addLeftBtn = nullptr;
    QPushButton* m_addRightBtn = nullptr;

    QListWidget* m_toolList = nullptr;
};

} // namespace editor
