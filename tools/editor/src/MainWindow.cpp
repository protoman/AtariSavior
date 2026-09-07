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

#include "MainWindow.hpp"
#include "DataSerializer.hpp"

#include <QMenuBar>
#include <QMenu>
#include <QToolBar>
#include <QStatusBar>
#include <QFileDialog>
#include <QMessageBox>
#include "AtariPalette.hpp"
#include <QHBoxLayout>
#include <QVBoxLayout>
#include <QGridLayout>
#include <QGroupBox>
#include <QRadioButton>
#include <QPushButton>
#include <QPainter>
#include <QApplication>
#include <QScrollArea>

namespace editor {

// Savannah Atari prototype room dims: 20 tiles wide (mirrored to 40), 12 tall
// (the bottom 4 rows are the grey HUD band).
static constexpr int kRoomWidth = 20;
static constexpr int kRoomHeight = 12;
// Centered passages carved for room connections.
static constexpr int kVertExitA = 8;   // vertical exit column range
static constexpr int kVertExitB = 11;
static constexpr int kHorizExitA = 6;  // horizontal exit row range
static constexpr int kHorizExitB = 9;

MainWindow::MainWindow(QWidget* parent) : QMainWindow(parent) {
    SetupUI();

    // Check / Prompt for Game Data Directory
    InitGameDataDir();

    // Populate stage combo from game data directory
    PopulateStageCombo();

    // Create initial level or load first stage
    if (m_stageCombo->count() > 0) {
        OnStageSelected(0);
    } else {
        NewLevel();
    }
}

MainWindow::~MainWindow() {}

void MainWindow::InitGameDataDir() {
    QSettings settings("SaviorSDL", "LevelEditor");
    m_gameDataDir = settings.value("gameDataDir").toString();

    if (m_gameDataDir.isEmpty() || !QDir(m_gameDataDir).exists()) {
        // Savannah Atari prototype keeps its level data in the repo's rooms/ folder.
        QString defaultPath;
        const QString cwd = QDir::currentPath();
        if (QDir(cwd + "/rooms").exists()) {
            defaultPath = cwd + "/rooms";
        } else if (QDir(cwd + "/../rooms").exists()) {
            defaultPath = cwd + "/../rooms";
        } else if (QDir(cwd + "/../../../rooms").exists()) {
            defaultPath = cwd + "/../../../rooms";
        } else {
            defaultPath = QDir::current().absoluteFilePath("assets/levels");
            if (!QDir(defaultPath).exists()) {
                defaultPath = QDir::current().absoluteFilePath("../assets/levels");
            }
        }

        if (!QDir(defaultPath).exists()) {
            QMessageBox::information(this, "Game Data Directory",
                "Please select the directory where stage JSON files are stored (e.g. the repo's rooms/ folder).");
        }

        QString dir = QFileDialog::getExistingDirectory(this,
            "Select Game Data Directory",
            QDir(defaultPath).exists() ? defaultPath : QDir::currentPath());

        if (!dir.isEmpty()) {
            m_gameDataDir = dir;
            settings.setValue("gameDataDir", m_gameDataDir);
        } else {
            m_gameDataDir = defaultPath;
        }
    }
}

void MainWindow::SelectGameDataDir() {
    QString dir = QFileDialog::getExistingDirectory(this,
        "Select Game Data Directory",
        m_gameDataDir);

    if (!dir.isEmpty()) {
        m_gameDataDir = dir;
        QSettings settings("SaviorSDL", "LevelEditor");
        settings.setValue("gameDataDir", m_gameDataDir);
        PopulateStageCombo();
        if (m_stageCombo->count() > 0) {
            OnStageSelected(0);
        }
    }
}

void MainWindow::SetupUI() {
    setWindowTitle("Savior SDL - H.E.R.O. Level Editor");
    resize(1180, 800);

    QWidget* centralWidget = new QWidget(this);
    QHBoxLayout* mainLayout = new QHBoxLayout(centralWidget);

    // Two-column tool area to the left of the map canvas:
    // column 1: stage selection, level settings, room navigation
    // column 2: tile & object tools
    QHBoxLayout* leftColumns = new QHBoxLayout();
    QVBoxLayout* col1 = new QVBoxLayout();
    QVBoxLayout* col2 = new QVBoxLayout();

    // Top-Left Stage Selection ComboBox
    QGroupBox* stageBox = new QGroupBox("Stage / Level Selection", this);
    QVBoxLayout* stageLayout = new QVBoxLayout(stageBox);

    m_stageCombo = new QComboBox(this);
    stageLayout->addWidget(m_stageCombo);

    QPushButton* changeDirBtn = new QPushButton("Data Folder Settings...", this);
    stageLayout->addWidget(changeDirBtn);

    col1->addWidget(stageBox);

    // Level Settings Box
    QGroupBox* levelPropBox = new QGroupBox("Level Settings", this);
    QVBoxLayout* levelPropLayout = new QVBoxLayout(levelPropBox);

    QHBoxLayout* idLayout = new QHBoxLayout();
    idLayout->addWidget(new QLabel("Level ID:"));
    m_levelIdSpin = new QSpinBox(this);
    m_levelIdSpin->setRange(1, 99);
    idLayout->addWidget(m_levelIdSpin);
    levelPropLayout->addLayout(idLayout);

    QHBoxLayout* nameLayout = new QHBoxLayout();
    nameLayout->addWidget(new QLabel("Name:"));
    m_levelNameEdit = new QLineEdit(this);
    nameLayout->addWidget(m_levelNameEdit);
    levelPropLayout->addLayout(nameLayout);

    m_colorBtn = new QPushButton("Cave Wall Color...", this);
    levelPropLayout->addWidget(m_colorBtn);

    col1->addWidget(levelPropBox);

    // Room Navigation & Directional Add Controls
    QGroupBox* roomBox = new QGroupBox("Room Navigation & Expansion", this);
    QVBoxLayout* roomLayout = new QVBoxLayout(roomBox);

    QHBoxLayout* roomNavLayout = new QHBoxLayout();
    roomNavLayout->addWidget(new QLabel("Select Room:"));
    m_roomCombo = new QComboBox(this);
    roomNavLayout->addWidget(m_roomCombo);
    roomLayout->addLayout(roomNavLayout);

    // Directional Add Room Grid
    QGroupBox* dirBox = new QGroupBox("Add Connected Room:", this);
    QGridLayout* dirGrid = new QGridLayout(dirBox);

    m_addUpBtn = new QPushButton("^ Above", this);
    m_addDownBtn = new QPushButton("v Below", this);
    m_addLeftBtn = new QPushButton("< Left", this);
    m_addRightBtn = new QPushButton("> Right", this);

    dirGrid->addWidget(m_addUpBtn, 0, 1);
    dirGrid->addWidget(m_addLeftBtn, 1, 0);
    dirGrid->addWidget(m_addRightBtn, 1, 2);
    dirGrid->addWidget(m_addDownBtn, 2, 1);

    roomLayout->addWidget(dirBox);

    QPushButton* remRoomBtn = new QPushButton("Remove Current Room", this);
    roomLayout->addWidget(remRoomBtn);

    col1->addWidget(roomBox);
    col1->addStretch();

    // Brush Tool Palette Box
    QGroupBox* brushBox = new QGroupBox("Tile and Object Tools", this);
    QVBoxLayout* brushLayout = new QVBoxLayout(brushBox);

    struct ToolInfo {
        BrushTool tool;
        QString text;
    };

    ToolInfo tools[] = {
        { BrushTool::SOLID_WALL, "1. Solid Rock Wall" },
        { BrushTool::FRAGILE_WALL, "2. Fragile Wall (Laser/Dynamite)" },
        { BrushTool::REINFORCED_WALL, "3. Reinforced Wall (Dynamite Only)" },
        { BrushTool::LAVA, "4. Lava Pool" },
        { BrushTool::WATER, "5. Water Pool" },
        { BrushTool::RAFT, "6. Floating Raft" },
        { BrushTool::MAGMA_FALL, "7. Magma Fall" },
        { BrushTool::ERASE_AIR, "0. Air (Erase)" },
        { BrushTool::SET_PLAYER_START, "P. Player Start" },
        { BrushTool::SET_MINER_GOAL, "M. Miner Goal" },
        { BrushTool::ADD_SPIDER, "S. Add Spider" },
        { BrushTool::ADD_BAT, "B. Add Bat" },
        { BrushTool::ADD_SNAKE, "K. Add Snake" },
        { BrushTool::ADD_TENTACLE, "T. Add Tentacle" },
        { BrushTool::ADD_MOTH, "W. Add Giant Moth" },
        { BrushTool::ADD_LAMP, "L. Add Lamp" },
        { BrushTool::DELETE_ENTITY, "X. Delete Entity" }
    };

    m_toolList = new QListWidget(this);
    m_toolList->setIconSize(QSize(28, 28));
    m_toolList->setSpacing(3);
    m_toolList->setUniformItemSizes(true);

    for (const auto& t : tools) {
        QListWidgetItem* item = new QListWidgetItem(t.text);
        item->setIcon(MakeToolIcon(t.tool));
        item->setData(Qt::UserRole, static_cast<int>(t.tool));
        m_toolList->addItem(item);
    }

    brushLayout->addWidget(m_toolList);

    col2->addWidget(brushBox);
    col2->addStretch();

    leftColumns->addLayout(col1, 1);
    leftColumns->addLayout(col2, 1);

    // Map Canvas, wrapped in a scroll area so the 40-column stage keeps its
    // natural size (each tile = m_tileSize px) and scrolls when the window is
    // smaller than the grid. Using a fixed-size canvas guarantees the mouse
    // click -> tile mapping matches the paint exactly.
    m_canvas = new MapCanvas(this);

    auto* scrollArea = new QScrollArea(this);
    scrollArea->setWidget(m_canvas);
    scrollArea->setWidgetResizable(false);
    scrollArea->setAlignment(Qt::AlignCenter);
    scrollArea->setMinimumWidth(400);

    mainLayout->addLayout(leftColumns, 0);
    mainLayout->addWidget(scrollArea, 1);

    setCentralWidget(centralWidget);

    // File Menu
    QMenu* fileMenu = menuBar()->addMenu("&File");
    fileMenu->addAction("&New Level", QKeySequence::New, this, &MainWindow::NewLevel);
    fileMenu->addAction("&Open Level...", QKeySequence::Open, this, &MainWindow::OpenLevel);
    fileMenu->addAction("&Save Level", QKeySequence::Save, this, &MainWindow::SaveLevel);
    fileMenu->addAction("Save Level &As...", QKeySequence::SaveAs, this, &MainWindow::SaveLevelAs);
    fileMenu->addSeparator();
    fileMenu->addAction("&Set Game Data Directory...", this, &MainWindow::SelectGameDataDir);
    fileMenu->addSeparator();
    fileMenu->addAction("E&xit", QKeySequence::Quit, qApp, &QApplication::quit);

    // Edit Menu (Undo)
    QMenu* editMenu = menuBar()->addMenu("&Edit");
    m_undoAction = editMenu->addAction("&Undo", QKeySequence::Undo, this, &MainWindow::PerformUndo);
    m_undoAction->setEnabled(false);

    // Status Bar
    statusBar()->showMessage("Ready");

    // Connections
    connect(m_canvas, &MapCanvas::levelModified, this, &MainWindow::OnLevelModified);
    connect(m_canvas, &MapCanvas::mouseMovedToTile, this, &MainWindow::OnMouseMovedToTile);

    connect(m_stageCombo, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &MainWindow::OnStageSelected);
    connect(m_roomCombo, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &MainWindow::OnRoomChanged);
    connect(changeDirBtn, &QPushButton::clicked, this, &MainWindow::SelectGameDataDir);

    connect(m_addUpBtn, &QPushButton::clicked, this, &MainWindow::AddRoomAbove);
    connect(m_addDownBtn, &QPushButton::clicked, this, &MainWindow::AddRoomBelow);
    connect(m_addLeftBtn, &QPushButton::clicked, this, &MainWindow::AddRoomLeft);
    connect(m_addRightBtn, &QPushButton::clicked, this, &MainWindow::AddRoomRight);
    connect(remRoomBtn, &QPushButton::clicked, this, &MainWindow::RemoveRoom);

    connect(m_colorBtn, &QPushButton::clicked, this, &MainWindow::PickWallColor);

    connect(m_toolList, &QListWidget::currentRowChanged, this, [this](int row) {
        QListWidgetItem* item = m_toolList->item(row);
        if (item) {
            m_canvas->SetCurrentBrush(static_cast<BrushTool>(item->data(Qt::UserRole).toInt()));
        }
    });
    if (m_toolList->currentRow() < 0) {
        m_toolList->setCurrentRow(0);
    } else {
        QListWidgetItem* item = m_toolList->currentItem();
        m_canvas->SetCurrentBrush(static_cast<BrushTool>(item->data(Qt::UserRole).toInt()));
    }

    connect(m_levelIdSpin, &QSpinBox::valueChanged, this, [this](int val) {
        if (val != m_levelData.level_id) {
            m_levelData.level_id = val;
            OnLevelModified();
        }
    });
    connect(m_levelNameEdit, &QLineEdit::textChanged, this, [this](const QString& text) {
        if (text.toStdString() != m_levelData.name) {
            m_levelData.name = text.toStdString();
            OnLevelModified();
        }
    });
}

bool MainWindow::RoomExistsAt(int rx, int ry) const {
    for (const auto& room : m_levelData.rooms) {
        if (room.room_x == rx && room.room_y == ry) return true;
    }
    return false;
}

bool MainWindow::HasExitInDirection(int roomIndex, int dirX, int dirY) const {
    if (roomIndex < 0 || roomIndex >= (int)m_levelData.rooms.size()) return false;
    const auto& room = m_levelData.rooms[roomIndex];

    if (dirY == -1) {
        for (int x = kVertExitA; x <= kVertExitB; ++x) {
            if (room.tiles[0 * kRoomWidth + x] == (int)hero::TileType::AIR) return true;
        }
    } else if (dirY == 1) {
        for (int x = kVertExitA; x <= kVertExitB; ++x) {
            if (room.tiles[(kRoomHeight - 1) * kRoomWidth + x] == (int)hero::TileType::AIR) return true;
        }
    } else if (dirX == -1) {
        for (int y = kHorizExitA; y <= kHorizExitB; ++y) {
            if (room.tiles[y * kRoomWidth + 0] == (int)hero::TileType::AIR) return true;
        }
    } else if (dirX == 1) {
        for (int y = kHorizExitA; y <= kHorizExitB; ++y) {
            if (room.tiles[y * kRoomWidth + kRoomWidth - 1] == (int)hero::TileType::AIR) return true;
        }
    }
    return false;
}

void MainWindow::UpdateRoomDirectionButtons() {
    int curIdx = m_roomCombo->currentIndex();
    if (curIdx < 0 || curIdx >= (int)m_levelData.rooms.size()) {
        m_addUpBtn->setEnabled(false);
        m_addDownBtn->setEnabled(false);
        m_addLeftBtn->setEnabled(false);
        m_addRightBtn->setEnabled(false);
        return;
    }

    const auto& curRoom = m_levelData.rooms[curIdx];
    int cx = curRoom.room_x;
    int cy = curRoom.room_y;

    m_addUpBtn->setEnabled(!RoomExistsAt(cx, cy - 1) && !HasExitInDirection(curIdx, 0, -1));
    m_addDownBtn->setEnabled(!RoomExistsAt(cx, cy + 1) && !HasExitInDirection(curIdx, 0, 1));
    m_addLeftBtn->setEnabled(!RoomExistsAt(cx - 1, cy) && !HasExitInDirection(curIdx, -1, 0));
    m_addRightBtn->setEnabled(!RoomExistsAt(cx + 1, cy) && !HasExitInDirection(curIdx, 1, 0));
}

void MainWindow::AddRoomAbove() { CreateRoomInDirection(0, -1); }
void MainWindow::AddRoomBelow() { CreateRoomInDirection(0, 1); }
void MainWindow::AddRoomLeft()  { CreateRoomInDirection(-1, 0); }
void MainWindow::AddRoomRight() { CreateRoomInDirection(1, 0); }

void MainWindow::CreateRoomInDirection(int dirX, int dirY) {
    int curIdx = m_roomCombo->currentIndex();
    if (curIdx < 0 || curIdx >= (int)m_levelData.rooms.size()) return;

    auto& curRoom = m_levelData.rooms[curIdx];
    int targetX = curRoom.room_x + dirX;
    int targetY = curRoom.room_y + dirY;

    if (RoomExistsAt(targetX, targetY) || HasExitInDirection(curIdx, dirX, dirY)) {
        QMessageBox::warning(this, "Room Exists", "A room or exit already exists in that direction!");
        return;
    }

    // Carve exit in current room
    if (dirY == -1) {
        for (int x = kVertExitA; x <= kVertExitB; ++x) curRoom.tiles[0 * kRoomWidth + x] = (int)hero::TileType::AIR;
    } else if (dirY == 1) {
        for (int x = kVertExitA; x <= kVertExitB; ++x) curRoom.tiles[(kRoomHeight - 1) * kRoomWidth + x] = (int)hero::TileType::AIR;
    } else if (dirX == -1) {
        for (int y = kHorizExitA; y <= kHorizExitB; ++y) curRoom.tiles[y * kRoomWidth + 0] = (int)hero::TileType::AIR;
    } else if (dirX == 1) {
        for (int y = kHorizExitA; y <= kHorizExitB; ++y) curRoom.tiles[y * kRoomWidth + kRoomWidth - 1] = (int)hero::TileType::AIR;
    }

    // Create new connected room
    hero::RoomData newRoom;
    newRoom.room_id = (int)m_levelData.rooms.size();
    newRoom.room_x = targetX;
    newRoom.room_y = targetY;
    newRoom.width = kRoomWidth;
    newRoom.height = kRoomHeight;
    newRoom.tiles.resize(kRoomWidth * kRoomHeight, (int)hero::TileType::AIR);

    // Border walls
    for (int x = 0; x < kRoomWidth; ++x) {
        newRoom.tiles[0 * kRoomWidth + x] = (int)hero::TileType::SOLID_WALL;
        newRoom.tiles[(kRoomHeight - 1) * kRoomWidth + x] = (int)hero::TileType::SOLID_WALL;
    }
    for (int y = 0; y < kRoomHeight; ++y) {
        newRoom.tiles[y * kRoomWidth + 0] = (int)hero::TileType::SOLID_WALL;
        newRoom.tiles[y * kRoomWidth + (kRoomWidth - 1)] = (int)hero::TileType::SOLID_WALL;
    }

    // Carve corresponding entry exit in new room
    if (dirY == -1) { // Adding Above -> open bottom of new room
        for (int x = kVertExitA; x <= kVertExitB; ++x) newRoom.tiles[(kRoomHeight - 1) * kRoomWidth + x] = (int)hero::TileType::AIR;
    } else if (dirY == 1) { // Adding Below -> open top of new room
        for (int x = kVertExitA; x <= kVertExitB; ++x) newRoom.tiles[0 * kRoomWidth + x] = (int)hero::TileType::AIR;
    } else if (dirX == -1) { // Adding Left -> open right of new room
        for (int y = kHorizExitA; y <= kHorizExitB; ++y) newRoom.tiles[y * kRoomWidth + (kRoomWidth - 1)] = (int)hero::TileType::AIR;
    } else if (dirX == 1) { // Adding Right -> open left of new room
        for (int y = kHorizExitA; y <= kHorizExitB; ++y) newRoom.tiles[y * kRoomWidth + 0] = (int)hero::TileType::AIR;
    }

    m_levelData.rooms.push_back(newRoom);
    OnLevelModified();
    UpdateUIFromLevel();
    m_roomCombo->setCurrentIndex((int)m_levelData.rooms.size() - 1);
}

void MainWindow::ResetUndoStack() {
    m_history.Reset(m_levelData);
    UpdateWindowTitleAndUndoState();
}

void MainWindow::PushUndoState() {
    m_history.Push(m_levelData);
    UpdateWindowTitleAndUndoState();
}

void MainWindow::PerformUndo() {
    hero::LevelData previous;
    if (m_history.Undo(previous)) {
        m_levelData = previous;
        UpdateUIFromLevel();
        UpdateWindowTitleAndUndoState();
        statusBar()->showMessage("Undo performed", 2000);
    }
}

void MainWindow::UpdateWindowTitleAndUndoState() {
    bool modified = IsModified();
    QString title = "Savior SDL - H.E.R.O. Level Editor";
    if (!m_currentFilePath.isEmpty()) {
        title += " - " + m_currentFilePath;
    }
    if (modified) {
        title += " *";
    }
    setWindowTitle(title);

    if (m_undoAction) {
        m_undoAction->setEnabled(m_history.CanUndo());
    }
}

void MainWindow::PopulateStageCombo() {
    m_ignoreComboEvents = true;
    m_stageCombo->clear();

    QDir dir(m_gameDataDir);
    QStringList filters;
    filters << "level_*.json" << "*.json";
    QStringList files = dir.entryList(filters, QDir::Files, QDir::Name);

    int selectIndex = -1;
    for (int i = 0; i < files.size(); ++i) {
        QString fullPath = dir.absoluteFilePath(files[i]);
        m_stageCombo->addItem(files[i], fullPath);
        if (fullPath == m_currentFilePath) {
            selectIndex = i;
        }
    }

    if (selectIndex >= 0) {
        m_stageCombo->setCurrentIndex(selectIndex);
    }

    m_ignoreComboEvents = false;
}

void MainWindow::OnStageSelected(int index) {
    if (m_ignoreComboEvents || index < 0) return;

    QString filePath = m_stageCombo->itemData(index).toString();
    if (filePath.isEmpty() || !QFile::exists(filePath)) return;

    if (filePath == m_currentFilePath && !IsModified()) return;

    if (IsModified()) {
        auto res = QMessageBox::question(this, "Unsaved Changes",
            "Save current level changes before switching stage?",
            QMessageBox::Yes | QMessageBox::No | QMessageBox::Cancel);
        if (res == QMessageBox::Yes) {
            SaveLevel();
        } else if (res == QMessageBox::Cancel) {
            PopulateStageCombo();
            return;
        }
    }

    hero::LevelData loaded;
    if (hero::DataSerializer::LoadLevelFromFile(loaded, filePath.toStdString())) {
        m_levelData = loaded;
        m_currentFilePath = filePath;
        ResetUndoStack();
        UpdateUIFromLevel();
        statusBar()->showMessage("Loaded " + filePath, 3000);
    }
}

void MainWindow::PopulateRoomCombo() {
    m_ignoreComboEvents = true;
    m_roomCombo->clear();

    int totalRooms = (int)m_levelData.rooms.size();
    for (int r = 0; r < totalRooms; ++r) {
        const auto& room = m_levelData.rooms[r];
        QString label = QString("Room %1 (%2,%3)").arg(r + 1).arg(room.room_x).arg(room.room_y);
        if (r == m_levelData.start_room) {
            label += " [Start]";
        }
        if (r == m_levelData.miner_room) {
            label += " [Miner]";
        }
        m_roomCombo->addItem(label, r);
    }

    m_ignoreComboEvents = false;
}

void MainWindow::NewLevel() {
    m_levelData = hero::LevelData();
    m_levelData.level_id = 1;
    m_levelData.name = "New Level";
    m_levelData.wall_r = 180;
    m_levelData.wall_g = 80;
    m_levelData.wall_b = 0;

    m_levelData.rooms.clear();
    for (int r = 0; r < 2; ++r) {
        hero::RoomData room;
        room.room_id = r;
        room.room_x = 0;
        room.room_y = r;
        room.width = kRoomWidth;
        room.height = kRoomHeight;
        room.tiles.resize(kRoomWidth * kRoomHeight, (int)hero::TileType::AIR);

        for (int x = 0; x < kRoomWidth; ++x) {
            room.tiles[0 * kRoomWidth + x] = (int)hero::TileType::SOLID_WALL;
            room.tiles[(kRoomHeight - 1) * kRoomWidth + x] = (int)hero::TileType::SOLID_WALL;
        }
        for (int y = 0; y < kRoomHeight; ++y) {
            room.tiles[y * kRoomWidth + 0] = (int)hero::TileType::SOLID_WALL;
            room.tiles[y * kRoomWidth + (kRoomWidth - 1)] = (int)hero::TileType::SOLID_WALL;
        }
        if (r == 0) {
            for (int x = kVertExitA; x <= kVertExitB; ++x) room.tiles[(kRoomHeight - 1) * kRoomWidth + x] = (int)hero::TileType::AIR;
        } else {
            for (int x = kVertExitA; x <= kVertExitB; ++x) room.tiles[0 * kRoomWidth + x] = (int)hero::TileType::AIR;
        }
        m_levelData.rooms.push_back(room);
    }

    m_levelData.start_room = 0;
    m_levelData.start_x = 8.0f;
    m_levelData.start_y = 2.0f;

    m_levelData.miner_room = 1;
    m_levelData.miner_x = 13.0f;
    m_levelData.miner_y = 10.0f;

    m_currentFilePath.clear();
    ResetUndoStack();
    UpdateUIFromLevel();
}

void MainWindow::OpenLevel() {
    QString path = QFileDialog::getOpenFileName(this, "Open H.E.R.O. Level JSON", m_gameDataDir, "JSON Level Files (*.json)");
    if (path.isEmpty()) return;

    hero::LevelData loaded;
    if (hero::DataSerializer::LoadLevelFromFile(loaded, path.toStdString())) {
        m_levelData = loaded;
        m_currentFilePath = path;
        ResetUndoStack();
        UpdateUIFromLevel();
        statusBar()->showMessage("Loaded " + path, 3000);
    } else {
        QMessageBox::critical(this, "Error", "Failed to load JSON level file!");
    }
}

void MainWindow::SaveLevel() {
    if (m_currentFilePath.isEmpty()) {
        SaveLevelAs();
    } else {
        if (hero::DataSerializer::SaveLevelToFile(m_levelData, m_currentFilePath.toStdString())) {
            m_history.SetClean();
            UpdateWindowTitleAndUndoState();
            statusBar()->showMessage("Saved " + m_currentFilePath, 3000);
        } else {
            QMessageBox::critical(this, "Error", "Failed to save level file!");
        }
    }
}

void MainWindow::SaveLevelAs() {
    QString defaultName = QString("level_%1.json").arg(m_levelData.level_id, 2, 10, QChar('0'));
    QString path = QFileDialog::getSaveFileName(this, "Save H.E.R.O. Level JSON", QDir(m_gameDataDir).filePath(defaultName), "JSON Level Files (*.json)");
    if (path.isEmpty()) return;

    m_currentFilePath = path;
    SaveLevel();
    PopulateStageCombo();
}

void MainWindow::RemoveRoom() {
    if (m_levelData.rooms.size() <= 1) {
        QMessageBox::warning(this, "Warning", "Cannot remove the last remaining room!");
        return;
    }

    int currentIdx = m_roomCombo->currentIndex();
    if (currentIdx < 0) currentIdx = 0;

    m_levelData.rooms.erase(m_levelData.rooms.begin() + currentIdx);

    if (currentIdx >= (int)m_levelData.rooms.size()) {
        currentIdx = (int)m_levelData.rooms.size() - 1;
    }

    OnLevelModified();
    UpdateUIFromLevel();
    m_roomCombo->setCurrentIndex(currentIdx);
}

void MainWindow::OnRoomChanged(int index) {
    if (m_ignoreComboEvents || index < 0) return;
    m_canvas->SetActiveRoom(index);
    UpdateRoomDirectionButtons();
}

QIcon MainWindow::MakeToolIcon(BrushTool tool) const {
    QPixmap pix(32, 32);
    pix.fill(Qt::transparent);

    QPainter p(&pix);
    p.setRenderHint(QPainter::Antialiasing);

    QRect r = pix.rect().adjusted(2, 2, -2, -2);
    QFont font = p.font();
    font.setBold(true);
    font.setPixelSize(16);
    p.setFont(font);

    switch (tool) {
        case BrushTool::SOLID_WALL: {
            QColor c(m_levelData.wall_r, m_levelData.wall_g, m_levelData.wall_b);
            p.fillRect(r, c);
            p.setPen(c.darker(160));
            for (int y = r.top() + r.height() / 3; y < r.bottom(); y += r.height() / 3) {
                p.drawLine(r.left(), y, r.right(), y);
            }
            break;
        }
        case BrushTool::FRAGILE_WALL:
            p.fillRect(r, QColor(210, 140, 50));
            p.setPen(QColor(140, 90, 30));
            p.drawLine(r.topLeft(), r.bottomRight());
            break;
        case BrushTool::REINFORCED_WALL:
            p.fillRect(r, QColor(160, 40, 40));
            p.setPen(QColor(220, 80, 80));
            p.drawRect(r.adjusted(4, 4, -4, -4));
            break;
        case BrushTool::LAVA:
            p.fillRect(r, QColor(220, 60, 0));
            break;
        case BrushTool::WATER:
            p.fillRect(r, QColor(0, 90, 180));
            break;
        case BrushTool::RAFT:
            p.fillRect(r, QColor(140, 80, 20));
            p.setPen(QColor(90, 50, 10));
            for (int x = r.left() + 4; x < r.right(); x += 6) {
                p.drawLine(x, r.top(), x, r.bottom());
            }
            break;
        case BrushTool::MAGMA_FALL:
            p.fillRect(r, QColor(255, 100, 0));
            break;
        case BrushTool::ERASE_AIR:
            p.setPen(QColor(70, 70, 85));
            p.drawRect(r);
            break;
        case BrushTool::SET_PLAYER_START:
        case BrushTool::SET_MINER_GOAL:
            p.setPen(QColor(70, 70, 85));
            p.drawRect(pix.rect().adjusted(1, 1, -1, -1));
            if (tool == BrushTool::SET_PLAYER_START) {
                p.setBrush(QColor(255, 220, 0));
                p.drawEllipse(r);
            } else {
                p.setBrush(QColor(255, 140, 180));
                p.drawEllipse(r);
            }
            p.setPen(Qt::black);
            p.drawText(r, Qt::AlignCenter, tool == BrushTool::SET_PLAYER_START ? "P" : "M");
            break;
        case BrushTool::ADD_SPIDER:
        case BrushTool::ADD_BAT:
        case BrushTool::ADD_SNAKE:
        case BrushTool::ADD_TENTACLE:
        case BrushTool::ADD_MOTH: {
            QColor eColor;
            QString label;
            switch (tool) {
                case BrushTool::ADD_SPIDER:   eColor = QColor(240, 200, 0);   label = "S"; break;
                case BrushTool::ADD_BAT:      eColor = QColor(220, 40, 60);   label = "B"; break;
                case BrushTool::ADD_SNAKE:    eColor = QColor(40, 200, 40);   label = "K"; break;
                case BrushTool::ADD_MOTH:     eColor = QColor(190, 160, 120); label = "M"; break;
                default:                      eColor = QColor(200, 60, 200);  label = "T"; break;
            }
            p.setBrush(eColor);
            p.setPen(Qt::black);
            p.drawRoundedRect(r, 6, 6);
            p.drawText(r, Qt::AlignCenter, label);
            break;
        }
        case BrushTool::ADD_LAMP:
            p.setPen(QColor(70, 70, 85));
            p.drawRect(pix.rect().adjusted(1, 1, -1, -1));
            // Glowing bulb on a small pole
            p.setBrush(QColor(255, 230, 80));
            p.setPen(Qt::black);
            p.drawEllipse(r.center().x() - 7, r.top() + 2, 14, 14);
            p.setPen(QColor(150, 150, 150));
            p.drawLine(r.center().x(), r.center().y() + 1, r.center().x(), r.bottom() - 3);
            p.fillRect(r.center().x() - 5, r.bottom() - 4, 10, 3, QColor(120, 120, 120));
            break;
        case BrushTool::DELETE_ENTITY:
            p.setPen(QColor(70, 70, 85));
            p.drawRect(pix.rect().adjusted(1, 1, -1, -1));
            p.setPen(QPen(QColor(220, 40, 60), 3));
            p.drawLine(r.topLeft(), r.bottomRight());
            p.drawLine(r.topRight(), r.bottomLeft());
            break;
    }

    return QIcon(pix);
}

void MainWindow::RefreshToolIcons() {
    if (!m_toolList) return;
    for (int i = 0; i < m_toolList->count(); ++i) {
        QListWidgetItem* item = m_toolList->item(i);
        auto tool = static_cast<BrushTool>(item->data(Qt::UserRole).toInt());
        item->setIcon(MakeToolIcon(tool));
    }
}

void MainWindow::PickWallColor() {
    QColor curColor(m_levelData.wall_r, m_levelData.wall_g, m_levelData.wall_b);
    int picked = PickNtscColor(this, curColor);
    if (picked >= 0) {
        QColor rgb = NtscRgbForByte(picked);
        m_levelData.wall_r = rgb.red();
        m_levelData.wall_g = rgb.green();
        m_levelData.wall_b = rgb.blue();
        QString style = QString("background-color: rgb(%1, %2, %3); color: white;")
                            .arg(rgb.red()).arg(rgb.green()).arg(rgb.blue());
        m_colorBtn->setStyleSheet(style);
        OnLevelModified();
        RefreshToolIcons();
        m_canvas->update();
    }
}

void MainWindow::OnLevelModified() {
    PushUndoState();
    UpdateRoomDirectionButtons();
}

void MainWindow::OnMouseMovedToTile(int tileX, int tileY) {
    statusBar()->showMessage(QString("Tile: (%1, %2)").arg(tileX).arg(tileY));
}

void MainWindow::UpdateUIFromLevel() {
    m_ignoreComboEvents = true;

    m_levelIdSpin->setValue(m_levelData.level_id);
    m_levelNameEdit->setText(QString::fromStdString(m_levelData.name));

    int roomIdx = m_canvas ? std::min(m_roomCombo ? m_roomCombo->currentIndex() : 0, (int)m_levelData.rooms.size() - 1) : 0;
    if (roomIdx < 0) roomIdx = 0;

    PopulateRoomCombo();
    m_roomCombo->setCurrentIndex(roomIdx);

    QString style = QString("background-color: rgb(%1, %2, %3); color: white;")
                        .arg(m_levelData.wall_r).arg(m_levelData.wall_g).arg(m_levelData.wall_b);
    m_colorBtn->setStyleSheet(style);

    if (m_canvas) {
        m_canvas->SetLevelData(&m_levelData, roomIdx);
    }

    m_ignoreComboEvents = false;

    UpdateRoomDirectionButtons();
}

} // namespace editor
