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

    // Load global models
    LoadModels();

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
        LoadModels();
        PopulateStageCombo();
        if (m_stageCombo->count() > 0) {
            OnStageSelected(0);
        }
    }
}

void MainWindow::LoadModels() {
    m_modelsFilePath = m_gameDataDir + "/models/models.json";
    if (!hero::DataSerializer::LoadModelsFromFile(m_models, m_modelsFilePath.toStdString())) {
        // No models file yet — create a default model
        if (m_models.empty()) {
            hero::ModelData defaultModel;
            defaultModel.id = 0;
            defaultModel.name = "Default Cave";
            defaultModel.width = 20;
            defaultModel.height = 12;
            defaultModel.tiles.resize(20 * 12, (int)hero::TileType::AIR);
            for (int x = 0; x < 20; ++x) {
                defaultModel.tiles[0 * 20 + x] = (int)hero::TileType::SOLID_WALL;
                defaultModel.tiles[11 * 20 + x] = (int)hero::TileType::SOLID_WALL;
            }
            for (int y = 0; y < 12; ++y) {
                defaultModel.tiles[y * 20 + 0] = (int)hero::TileType::SOLID_WALL;
                defaultModel.tiles[y * 20 + 19] = (int)hero::TileType::SOLID_WALL;
            }
            m_models.push_back(defaultModel);
            SaveModels();
        }
    }
    PopulateModelCombo();
    if (m_modelList->count() > 0 && m_modelList->currentRow() < 0) {
        m_modelList->setCurrentRow(0);
    }
}

void MainWindow::SaveModels() {
    // Ensure directory exists
    QDir dir = QFileInfo(m_modelsFilePath).absoluteDir();
    if (!dir.exists()) dir.mkpath(".");
    hero::DataSerializer::SaveModelsToFile(m_models, m_modelsFilePath.toStdString());
}

void MainWindow::SetupUI() {
    setWindowTitle("Savior AI - Level Editor");
    resize(1200, 800);

    QWidget* centralWidget = new QWidget(this);
    QHBoxLayout* mainLayout = new QHBoxLayout(centralWidget);

    // Tab widget at the top — controls ALL left panel content
    m_tabWidget = new QTabWidget(this);

    // ===== MODEL TAB =====
    QWidget* modelTab = new QWidget();
    QVBoxLayout* modelTabLayout = new QVBoxLayout(modelTab);

    QGroupBox* modelListBox = new QGroupBox("Room Models", this);
    QVBoxLayout* modelListLayout = new QVBoxLayout(modelListBox);
    m_modelList = new QListWidget(this);
    modelListLayout->addWidget(m_modelList);
    QHBoxLayout* modelBtnLayout = new QHBoxLayout();
    QPushButton* addModelBtn = new QPushButton("+ Add Model", this);
    QPushButton* remModelBtn = new QPushButton("- Remove", this);
    modelBtnLayout->addWidget(addModelBtn);
    modelBtnLayout->addWidget(remModelBtn);
    modelListLayout->addLayout(modelBtnLayout);
    modelTabLayout->addWidget(modelListBox);

    QGroupBox* modelToolBox = new QGroupBox("Wall Tools", this);
    QVBoxLayout* modelToolLayout = new QVBoxLayout(modelToolBox);
    m_modelToolList = new QListWidget(this);
    m_modelToolList->setIconSize(QSize(28, 28));
    m_modelToolList->setSpacing(3);
    m_modelToolList->setUniformItemSizes(true);
    struct ToolInfo { BrushTool tool; QString text; };
    ToolInfo modelTools[] = {
        { BrushTool::SOLID_WALL, "1. Solid Rock Wall" },
        { BrushTool::HOT_ROCK_WALL, "2. Hot Rock Wall" },
        { BrushTool::ERASE_AIR, "0. Air (Erase)" },
    };
    for (const auto& t : modelTools) {
        QListWidgetItem* item = new QListWidgetItem(t.text);
        item->setIcon(MakeToolIcon(t.tool));
        item->setData(Qt::UserRole, static_cast<int>(t.tool));
        m_modelToolList->addItem(item);
    }
    modelToolLayout->addWidget(m_modelToolList);
    modelTabLayout->addWidget(modelToolBox);
    modelTabLayout->addStretch();

    m_tabWidget->addTab(modelTab, "Model");

    // ===== LEVEL TAB =====
    QWidget* levelTab = new QWidget();
    QVBoxLayout* levelTabLayout = new QVBoxLayout(levelTab);

    // Stage Selection
    QGroupBox* stageBox = new QGroupBox("Stage / Level", this);
    QVBoxLayout* stageLayout = new QVBoxLayout(stageBox);
    m_stageCombo = new QComboBox(this);
    stageLayout->addWidget(m_stageCombo);
    levelTabLayout->addWidget(stageBox);

    // Level Settings
    QGroupBox* levelPropBox = new QGroupBox("Level Settings", this);
    QVBoxLayout* levelPropLayout = new QVBoxLayout(levelPropBox);
    QHBoxLayout* colorLayout = new QHBoxLayout();
    m_colorBtn = new QPushButton("Color 1", this);
    colorLayout->addWidget(m_colorBtn);
    m_colorBtn2 = new QPushButton("Color 2", this);
    colorLayout->addWidget(m_colorBtn2);
    levelPropLayout->addLayout(colorLayout);
    levelTabLayout->addWidget(levelPropBox);

    // Room Navigation
    QGroupBox* roomBox = new QGroupBox("Rooms", this);
    QVBoxLayout* roomLayout = new QVBoxLayout(roomBox);
    QHBoxLayout* roomNavLayout = new QHBoxLayout();
    roomNavLayout->addWidget(new QLabel("Room:"));
    m_roomCombo = new QComboBox(this);
    roomNavLayout->addWidget(m_roomCombo);
    roomLayout->addLayout(roomNavLayout);
    QGroupBox* dirBox = new QGroupBox("Add Room:", this);
    QHBoxLayout* dirRow = new QHBoxLayout(dirBox);
    m_addLeftBtn = new QPushButton("<", this);
    m_addUpBtn = new QPushButton("^", this);
    m_addDownBtn = new QPushButton("v", this);
    m_addRightBtn = new QPushButton(">", this);
    dirRow->addWidget(m_addLeftBtn);
    dirRow->addWidget(m_addUpBtn);
    dirRow->addWidget(m_addDownBtn);
    dirRow->addWidget(m_addRightBtn);
    roomLayout->addWidget(dirBox);
    QPushButton* remRoomBtn = new QPushButton("Remove Room", this);
    roomLayout->addWidget(remRoomBtn);

    // Bottom band: optional colored strip on tile row 11 of current room
    QHBoxLayout* bandLayout = new QHBoxLayout();
    m_bottomBandCheck = new QCheckBox("Bottom band", this);
    m_bottomBandCheck->setToolTip("Colored death band on the room's bottom tile row");
    bandLayout->addWidget(m_bottomBandCheck);
    m_bandColorBtn = new QPushButton("Band color", this);
    m_bandColorBtn->setToolTip("NTSC color for the bottom band (when enabled)");
    bandLayout->addWidget(m_bandColorBtn);
    roomLayout->addLayout(bandLayout);
    levelTabLayout->addWidget(roomBox);

    // Model Assignment
    QGroupBox* modelAssignBox = new QGroupBox("Room Model", this);
    QVBoxLayout* modelAssignLayout = new QVBoxLayout(modelAssignBox);
    QHBoxLayout* assignRow = new QHBoxLayout();
    assignRow->addWidget(new QLabel("Model:"));
    m_modelAssignCombo = new QComboBox(this);
    assignRow->addWidget(m_modelAssignCombo);
    modelAssignLayout->addLayout(assignRow);
    levelTabLayout->addWidget(modelAssignBox);

    // Entity Tools
    QGroupBox* levelToolBox = new QGroupBox("Entity Tools", this);
    QVBoxLayout* levelToolLayout = new QVBoxLayout(levelToolBox);
    m_levelToolList = new QListWidget(this);
    m_levelToolList->setIconSize(QSize(28, 28));
    m_levelToolList->setSpacing(3);
    m_levelToolList->setUniformItemSizes(true);
    ToolInfo levelTools[] = {
        { BrushTool::SET_MINER_GOAL, "M. Miner Goal" },
        { BrushTool::ADD_SPIDER, "S. Spider" },
        { BrushTool::ADD_BAT, "B. Bat" },
        { BrushTool::ADD_SNAKE, "K. Snake" },
        { BrushTool::ADD_TENTACLE, "T. Tentacle" },
        { BrushTool::ADD_MOTH, "W. Moth" },
        { BrushTool::ADD_LAMP, "L. Lamp" },
        { BrushTool::ADD_RAFT, "R. Raft" },
        { BrushTool::DELETE_ENTITY, "X. Delete" }
    };
    for (const auto& t : levelTools) {
        QListWidgetItem* item = new QListWidgetItem(t.text);
        item->setIcon(MakeToolIcon(t.tool));
        item->setData(Qt::UserRole, static_cast<int>(t.tool));
        m_levelToolList->addItem(item);
    }
    levelToolLayout->addWidget(m_levelToolList);

    m_facingBtn = new QPushButton("Initial facing: → (F)", this);
    m_facingBtn->setToolTip(
        "Direction new enemies face (snake/moth first move).\n"
        "F on canvas or this button toggles. Click an existing enemy with an "
        "enemy brush to flip it.");
    levelToolLayout->addWidget(m_facingBtn);

    levelTabLayout->addWidget(levelToolBox);

    m_tabWidget->addTab(levelTab, "Level");

    // Canvas (shared between modes)
    m_canvas = new MapCanvas(this);
    auto* scrollArea = new QScrollArea(this);
    scrollArea->setWidget(m_canvas);
    scrollArea->setWidgetResizable(false);
    scrollArea->setAlignment(Qt::AlignCenter);
    scrollArea->setMinimumWidth(400);

    mainLayout->addWidget(m_tabWidget, 0);
    mainLayout->addWidget(scrollArea, 1);

    setCentralWidget(centralWidget);

    // Menus
    QMenu* fileMenu = menuBar()->addMenu("&File");
    fileMenu->addAction("&New Level", QKeySequence::New, this, &MainWindow::NewLevel);
    fileMenu->addAction("&Open Level...", QKeySequence::Open, this, &MainWindow::OpenLevel);
    fileMenu->addAction("&Save Level", QKeySequence::Save, this, &MainWindow::SaveLevel);
    fileMenu->addAction("Save Level &As...", QKeySequence::SaveAs, this, &MainWindow::SaveLevelAs);
    fileMenu->addSeparator();
    fileMenu->addAction("&Set Game Data Directory...", this, &MainWindow::SelectGameDataDir);
    fileMenu->addSeparator();
    fileMenu->addAction("E&xit", QKeySequence::Quit, qApp, &QApplication::quit);

    QMenu* editMenu = menuBar()->addMenu("&Edit");
    m_undoAction = editMenu->addAction("&Undo", QKeySequence::Undo, this, &MainWindow::PerformUndo);
    m_undoAction->setEnabled(false);

    statusBar()->showMessage("Ready");

    // Connections
    connect(m_canvas, &MapCanvas::levelModified, this, &MainWindow::OnLevelModified);
    connect(m_canvas, &MapCanvas::mouseMovedToTile, this, &MainWindow::OnMouseMovedToTile);
    connect(m_canvas, &MapCanvas::facingChanged, this, &MainWindow::OnFacingChanged);
    connect(m_facingBtn, &QPushButton::clicked, this, &MainWindow::ToggleInitialFacing);
    connect(m_stageCombo, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &MainWindow::OnStageSelected);
    connect(m_roomCombo, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &MainWindow::OnRoomChanged);
    connect(m_modelAssignCombo, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &MainWindow::OnModelAssignmentChanged);
    connect(m_tabWidget, &QTabWidget::currentChanged, this, &MainWindow::OnTabChanged);
    connect(m_addUpBtn, &QPushButton::clicked, this, &MainWindow::AddRoomAbove);
    connect(m_addDownBtn, &QPushButton::clicked, this, &MainWindow::AddRoomBelow);
    connect(m_addLeftBtn, &QPushButton::clicked, this, &MainWindow::AddRoomLeft);
    connect(m_addRightBtn, &QPushButton::clicked, this, &MainWindow::AddRoomRight);
    connect(remRoomBtn, &QPushButton::clicked, this, &MainWindow::RemoveRoom);
    connect(m_colorBtn, &QPushButton::clicked, this, &MainWindow::PickWallColor);
    connect(m_colorBtn2, &QPushButton::clicked, this, &MainWindow::PickWallColor2);
    connect(m_bandColorBtn, &QPushButton::clicked, this, &MainWindow::PickBandColor);
    connect(m_bottomBandCheck, &QCheckBox::toggled, this, &MainWindow::OnBottomBandToggled);
    connect(addModelBtn, &QPushButton::clicked, this, &MainWindow::AddModel);
    connect(remModelBtn, &QPushButton::clicked, this, &MainWindow::RemoveModel);
    connect(m_modelList, &QListWidget::currentRowChanged, this, &MainWindow::OnModelSelected);

    connect(m_modelToolList, &QListWidget::currentRowChanged, this, [this](int row) {
        QListWidgetItem* item = m_modelToolList->item(row);
        if (item) {
            m_canvas->SetCurrentBrush(static_cast<BrushTool>(item->data(Qt::UserRole).toInt()));
        }
    });
    connect(m_levelToolList, &QListWidget::currentRowChanged, this, [this](int row) {
        QListWidgetItem* item = m_levelToolList->item(row);
        if (item) {
            m_canvas->SetCurrentBrush(static_cast<BrushTool>(item->data(Qt::UserRole).toInt()));
        }
    });
    if (m_modelToolList->count() > 0) {
        m_modelToolList->setCurrentRow(0);
    }

    // Start in Model mode
    SwitchEditMode(EditMode::MODEL_EDIT);
}

void MainWindow::SwitchEditMode(EditMode mode) {
    m_editMode = mode;
    m_canvas->SetEditMode(mode == EditMode::MODEL_EDIT);
    if (mode == EditMode::MODEL_EDIT) {
        m_tabWidget->setCurrentIndex(0);
        // Select first model tool if none selected
        if (m_modelToolList->currentRow() < 0 && m_modelToolList->count() > 0) {
            m_modelToolList->setCurrentRow(0);
        }
    } else {
        m_tabWidget->setCurrentIndex(1);
        UpdateRoomDirectionButtons();
        // Select first level tool if none selected
        if (m_levelToolList->currentRow() < 0 && m_levelToolList->count() > 0) {
            m_levelToolList->setCurrentRow(0);
        }
    }
}

void MainWindow::OnTabChanged(int index) {
    SwitchEditMode(index == 0 ? EditMode::MODEL_EDIT : EditMode::LEVEL_EDIT);
}

void MainWindow::OnModelSelected(int index) {
    if (m_editMode != EditMode::MODEL_EDIT) return;
    if (index < 0 || index >= (int)m_models.size()) return;
    m_canvas->SetActiveModel(index);
}

void MainWindow::OnModelAssignmentChanged(int modelIdx) {
    if (m_ignoreComboEvents) return;
    if (m_editMode != EditMode::LEVEL_EDIT) return;
    int roomIdx = m_roomCombo->currentIndex();
    if (roomIdx < 0 || roomIdx >= (int)m_levelData.rooms.size()) return;
    if (modelIdx < 0 || modelIdx >= (int)m_models.size()) return;
    m_levelData.rooms[roomIdx].model_id = modelIdx;
    OnLevelModified();
    m_canvas->update();
}

void MainWindow::AddModel() {
    hero::ModelData newModel;
    newModel.id = (int)m_models.size();
    newModel.name = "Model " + std::to_string(newModel.id + 1);
    newModel.width = 20;
    newModel.height = 12;
    newModel.tiles.resize(20 * 12, (int)hero::TileType::AIR);
    for (int x = 0; x < 20; ++x) {
        newModel.tiles[0 * 20 + x] = (int)hero::TileType::SOLID_WALL;
        newModel.tiles[11 * 20 + x] = (int)hero::TileType::SOLID_WALL;
    }
    for (int y = 0; y < 12; ++y) {
        newModel.tiles[y * 20 + 0] = (int)hero::TileType::SOLID_WALL;
        newModel.tiles[y * 20 + 19] = (int)hero::TileType::SOLID_WALL;
    }
    m_models.push_back(newModel);
    SaveModels();
    PopulateModelCombo();
    m_modelList->setCurrentRow((int)m_models.size() - 1);
}

void MainWindow::RemoveModel() {
    if (m_models.size() <= 1) {
        QMessageBox::warning(this, "Warning", "Cannot remove the last model!");
        return;
    }
    int idx = m_modelList->currentRow();
    if (idx < 0 || idx >= (int)m_models.size()) return;
    // Check if any room in any level uses this model — for now just check current level
    for (const auto& room : m_levelData.rooms) {
        if (room.model_id == idx) {
            QMessageBox::warning(this, "Warning", "Cannot remove a model that is assigned to a room in the current level!");
            return;
        }
    }
    m_models.erase(m_models.begin() + idx);
    // Fix model_id references > idx in current level
    for (auto& room : m_levelData.rooms) {
        if (room.model_id > idx) room.model_id--;
    }
    SaveModels();
    PopulateModelCombo();
    if (idx >= (int)m_models.size()) idx = (int)m_models.size() - 1;
    m_modelList->setCurrentRow(idx);
}

void MainWindow::PopulateModelCombo() {
    m_ignoreComboEvents = true;
    int prevIdx = m_modelAssignCombo->currentIndex();
    m_modelAssignCombo->clear();
    m_modelList->clear();
    for (int i = 0; i < (int)m_models.size(); ++i) {
        const auto& m = m_models[i];
        QString label = QString("Model %1: %2 (%3x%4)").arg(i + 1).arg(QString::fromStdString(m.name)).arg(m.width).arg(m.height);
        m_modelAssignCombo->addItem(label, i);
        m_modelList->addItem(label);
    }
    if (prevIdx >= 0 && prevIdx < m_modelAssignCombo->count()) {
        m_modelAssignCombo->setCurrentIndex(prevIdx);
    }
    m_ignoreComboEvents = false;
}

bool MainWindow::RoomExistsAt(int rx, int ry) const {
    for (const auto& room : m_levelData.rooms) {
        if (room.room_x == rx && room.room_y == ry) return true;
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

    m_addUpBtn->setEnabled(!RoomExistsAt(cx, cy - 1));
    m_addDownBtn->setEnabled(!RoomExistsAt(cx, cy + 1));
    m_addLeftBtn->setEnabled(!RoomExistsAt(cx - 1, cy));
    m_addRightBtn->setEnabled(!RoomExistsAt(cx + 1, cy));
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

    if (RoomExistsAt(targetX, targetY)) {
        QMessageBox::warning(this, "Room Exists", "A room already exists in that direction!");
        return;
    }

    // Get current room's model to carve exit
    int curModelId = curRoom.model_id;
    if (curModelId < 0 || curModelId >= (int)m_models.size()) return;
    auto& curModel = m_models[curModelId];

    // Carve exit in current room's model
    if (dirY == -1) {
        for (int x = kVertExitA; x <= kVertExitB; ++x) curModel.tiles[0 * kRoomWidth + x] = (int)hero::TileType::AIR;
    } else if (dirY == 1) {
        for (int x = kVertExitA; x <= kVertExitB; ++x) curModel.tiles[(kRoomHeight - 1) * kRoomWidth + x] = (int)hero::TileType::AIR;
    } else if (dirX == -1) {
        for (int y = kHorizExitA; y <= kHorizExitB; ++y) curModel.tiles[y * kRoomWidth + 0] = (int)hero::TileType::AIR;
    } else if (dirX == 1) {
        for (int y = kHorizExitA; y <= kHorizExitB; ++y) curModel.tiles[y * kRoomWidth + (kRoomWidth - 1)] = (int)hero::TileType::AIR;
    }

    // Create new model for the new room
    int newModelId = (int)m_models.size();
    hero::ModelData newModel;
    newModel.id = newModelId;
    newModel.name = "Model " + std::to_string(newModelId + 1);
    newModel.width = kRoomWidth;
    newModel.height = kRoomHeight;
    newModel.tiles.resize(kRoomWidth * kRoomHeight, (int)hero::TileType::AIR);

    // Border walls
    for (int x = 0; x < kRoomWidth; ++x) {
        newModel.tiles[0 * kRoomWidth + x] = (int)hero::TileType::SOLID_WALL;
        newModel.tiles[(kRoomHeight - 1) * kRoomWidth + x] = (int)hero::TileType::SOLID_WALL;
    }
    for (int y = 0; y < kRoomHeight; ++y) {
        newModel.tiles[y * kRoomWidth + 0] = (int)hero::TileType::SOLID_WALL;
        newModel.tiles[y * kRoomWidth + (kRoomWidth - 1)] = (int)hero::TileType::SOLID_WALL;
    }

    // Carve entry in new room
    if (dirY == -1) {
        for (int x = kVertExitA; x <= kVertExitB; ++x) newModel.tiles[(kRoomHeight - 1) * kRoomWidth + x] = (int)hero::TileType::AIR;
    } else if (dirY == 1) {
        for (int x = kVertExitA; x <= kVertExitB; ++x) newModel.tiles[0 * kRoomWidth + x] = (int)hero::TileType::AIR;
    } else if (dirX == -1) {
        for (int y = kHorizExitA; y <= kHorizExitB; ++y) newModel.tiles[y * kRoomWidth + (kRoomWidth - 1)] = (int)hero::TileType::AIR;
    } else if (dirX == 1) {
        for (int y = kHorizExitA; y <= kHorizExitB; ++y) newModel.tiles[y * kRoomWidth + 0] = (int)hero::TileType::AIR;
    }

    m_models.push_back(newModel);
    SaveModels(); // Save global models after adding new model and carving exits

    // Create room referencing new model
    hero::RoomData newRoom;
    newRoom.room_id = (int)m_levelData.rooms.size();
    newRoom.model_id = newModelId;
    newRoom.room_x = targetX;
    newRoom.room_y = targetY;
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
    QString title = "Savior AI - Level Editor";
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
    m_levelData.wall2_r = 40;
    m_levelData.wall2_g = 130;
    m_levelData.wall2_b = 90;
    m_levelData.start_room = 0;
    m_levelData.miner_room = -1;
    m_levelData.miner_x = 0;
    m_levelData.miner_y = 0;

    // Create rooms referencing global model 0
    m_levelData.rooms.clear();
    for (int r = 0; r < 2; ++r) {
        hero::RoomData room;
        room.room_id = r;
        room.model_id = 0; // use first global model
        room.room_x = 0;
        room.room_y = r;
        m_levelData.rooms.push_back(room);
    }

    m_levelData.start_room = 0;
    m_levelData.miner_room = 1;
    m_levelData.miner_x = 13.0f;
    m_levelData.miner_y = 10.0f;

    m_currentFilePath.clear();
    ResetUndoStack();
    UpdateUIFromLevel();
}

void MainWindow::OpenLevel() {
    QString path = QFileDialog::getOpenFileName(this, "Open S.A.V.I.O.R. Level JSON", m_gameDataDir, "JSON Level Files (*.json)");
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
    QString path = QFileDialog::getSaveFileName(this, "Save S.A.V.I.O.R. Level JSON", QDir(m_gameDataDir).filePath(defaultName), "JSON Level Files (*.json)");
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
    // Sync model assignment combo to this room's model
    if (index < (int)m_levelData.rooms.size()) {
        int mid = m_levelData.rooms[index].model_id;
        m_ignoreComboEvents = true;
        if (mid >= 0 && mid < m_modelAssignCombo->count()) {
            m_modelAssignCombo->setCurrentIndex(mid);
        }
        m_ignoreComboEvents = false;
    }
    // Sync bottom-band controls to newly selected room
    if (index < (int)m_levelData.rooms.size()) {
        const auto& room = m_levelData.rooms[index];
        m_bottomBandCheck->setChecked(room.bottom_band);
        QString bandStyle = QString("background-color: rgb(%1, %2, %3); color: white;")
                                .arg(room.bottom_r).arg(room.bottom_g).arg(room.bottom_b);
        m_bandColorBtn->setStyleSheet(bandStyle);
        m_bandColorBtn->setEnabled(room.bottom_band);
    }
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
        case BrushTool::HOT_ROCK_WALL: {
            p.fillRect(r, QColor(255, 80, 20));
            p.setPen(QColor(255, 220, 80));
            for (int y = r.top() + r.height() / 3; y < r.bottom(); y += r.height() / 3) {
                p.drawLine(r.left(), y, r.right(), y);
            }
            break;
        }
        case BrushTool::ERASE_AIR:
            p.setPen(QColor(70, 70, 85));
            p.drawRect(r);
            break;
        case BrushTool::SET_MINER_GOAL:
            p.setPen(QColor(70, 70, 85));
            p.drawRect(pix.rect().adjusted(1, 1, -1, -1));
            p.setBrush(QColor(255, 140, 180));
            p.drawEllipse(r);
            p.setPen(Qt::black);
            p.drawText(r, Qt::AlignCenter, "M");
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
            p.setBrush(QColor(255, 230, 80));
            p.setPen(Qt::black);
            p.drawEllipse(r.center().x() - 7, r.top() + 2, 14, 14);
            p.setPen(QColor(150, 150, 150));
            p.drawLine(r.center().x(), r.center().y() + 1, r.center().x(), r.bottom() - 3);
            p.fillRect(r.center().x() - 5, r.bottom() - 4, 10, 3, QColor(120, 120, 120));
            break;
        case BrushTool::ADD_RAFT:
            p.fillRect(r, QColor(140, 80, 20));
            p.setPen(QColor(90, 50, 10));
            for (int x = r.left() + 4; x < r.right(); x += 6) {
                p.drawLine(x, r.top(), x, r.bottom());
            }
            break;
        case BrushTool::ADD_MAGMA:
            p.fillRect(r, QColor(255, 100, 0));
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
    auto refreshList = [this](QListWidget* list) {
        if (!list) return;
        for (int i = 0; i < list->count(); ++i) {
            QListWidgetItem* item = list->item(i);
            auto tool = static_cast<BrushTool>(item->data(Qt::UserRole).toInt());
            item->setIcon(MakeToolIcon(tool));
        }
    };
    refreshList(m_modelToolList);
    refreshList(m_levelToolList);
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

void MainWindow::PickWallColor2() {
    QColor curColor(m_levelData.wall2_r, m_levelData.wall2_g, m_levelData.wall2_b);
    int picked = PickNtscColor(this, curColor);
    if (picked >= 0) {
        QColor rgb = NtscRgbForByte(picked);
        m_levelData.wall2_r = rgb.red();
        m_levelData.wall2_g = rgb.green();
        m_levelData.wall2_b = rgb.blue();
        QString style = QString("background-color: rgb(%1, %2, %3); color: white;")
                            .arg(rgb.red()).arg(rgb.green()).arg(rgb.blue());
        m_colorBtn2->setStyleSheet(style);
        OnLevelModified();
        RefreshToolIcons();
        m_canvas->update();
    }
}

void MainWindow::PickBandColor() {
    int roomIdx = m_roomCombo ? m_roomCombo->currentIndex() : -1;
    if (roomIdx < 0 || roomIdx >= (int)m_levelData.rooms.size()) return;
    auto& room = m_levelData.rooms[roomIdx];
    QColor curColor(room.bottom_r, room.bottom_g, room.bottom_b);
    int picked = PickNtscColor(this, curColor);
    if (picked >= 0) {
        QColor rgb = NtscRgbForByte(picked);
        room.bottom_r = rgb.red();
        room.bottom_g = rgb.green();
        room.bottom_b = rgb.blue();
        room.bottom_band = true;
        if (m_bottomBandCheck) m_bottomBandCheck->setChecked(true);
        QString style = QString("background-color: rgb(%1, %2, %3); color: white;")
                            .arg(rgb.red()).arg(rgb.green()).arg(rgb.blue());
        m_bandColorBtn->setStyleSheet(style);
        OnLevelModified();
        m_canvas->update();
    }
}

void MainWindow::OnBottomBandToggled(bool checked) {
    if (m_bandColorBtn) m_bandColorBtn->setEnabled(checked);
    if (m_ignoreComboEvents) return;
    int roomIdx = m_roomCombo ? m_roomCombo->currentIndex() : -1;
    if (roomIdx < 0 || roomIdx >= (int)m_levelData.rooms.size()) return;
    auto& room = m_levelData.rooms[roomIdx];
    if (room.bottom_band == checked) return;
    room.bottom_band = checked;
    OnLevelModified();
    m_canvas->update();
}

void MainWindow::OnLevelModified() {
    if (m_editMode == EditMode::MODEL_EDIT) {
        // Model edits: save global models file
        SaveModels();
    } else {
        // Level edits: push undo state
        PushUndoState();
        UpdateRoomDirectionButtons();
    }
}

void MainWindow::OnMouseMovedToTile(int tileX, int tileY) {
    statusBar()->showMessage(QString("Tile: (%1, %2)").arg(tileX).arg(tileY));
}

void MainWindow::OnFacingChanged(int dir) {
    if (m_facingBtn)
        m_facingBtn->setText(dir >= 0 ? "Initial facing: → (F)"
                                      : "Initial facing: ← (F)");
}

void MainWindow::ToggleInitialFacing() {
    if (!m_canvas) return;
    m_canvas->SetInitialFacing(-m_canvas->InitialFacing());
    OnFacingChanged(m_canvas->InitialFacing());
}

void MainWindow::UpdateUIFromLevel() {
    m_ignoreComboEvents = true;

    int roomIdx = m_canvas ? std::min(m_roomCombo ? m_roomCombo->currentIndex() : 0, (int)m_levelData.rooms.size() - 1) : 0;
    if (roomIdx < 0) roomIdx = 0;

    PopulateRoomCombo();
    PopulateModelCombo();
    m_roomCombo->setCurrentIndex(roomIdx);

    // Sync model assignment combo to current room's model_id
    if (roomIdx >= 0 && roomIdx < (int)m_levelData.rooms.size()) {
        int mid = m_levelData.rooms[roomIdx].model_id;
        if (mid >= 0 && mid < m_modelAssignCombo->count()) {
            m_modelAssignCombo->setCurrentIndex(mid);
        }
    }

    QString style = QString("background-color: rgb(%1, %2, %3); color: white;")
                        .arg(m_levelData.wall_r).arg(m_levelData.wall_g).arg(m_levelData.wall_b);
    m_colorBtn->setStyleSheet(style);
    QString style2 = QString("background-color: rgb(%1, %2, %3); color: white;")
                         .arg(m_levelData.wall2_r).arg(m_levelData.wall2_g).arg(m_levelData.wall2_b);
    m_colorBtn2->setStyleSheet(style2);

    // Sync bottom-band controls to current room
    if (roomIdx >= 0 && roomIdx < (int)m_levelData.rooms.size()) {
        const auto& room = m_levelData.rooms[roomIdx];
        m_bottomBandCheck->setChecked(room.bottom_band);
        QString bandStyle = QString("background-color: rgb(%1, %2, %3); color: white;")
                                .arg(room.bottom_r).arg(room.bottom_g).arg(room.bottom_b);
        m_bandColorBtn->setStyleSheet(bandStyle);
        m_bandColorBtn->setEnabled(room.bottom_band);
    }

    if (m_canvas) {
        m_canvas->SetLevelData(&m_levelData, &m_models, roomIdx);
    }

    m_ignoreComboEvents = false;

    UpdateRoomDirectionButtons();
}

} // namespace editor
