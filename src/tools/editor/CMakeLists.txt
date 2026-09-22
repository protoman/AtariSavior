cmake_minimum_required(VERSION 3.20)
project(savior_editor VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

# Find Qt6
find_package(Qt6 REQUIRED COMPONENTS Widgets Core Gui)

# Fetch Cereal for JSON serialization if not already present
if (NOT TARGET cereal)
    set(JUST_INSTALL_CEREAL ON CACHE BOOL "" FORCE)
    set(BUILD_SANDBOX OFF CACHE BOOL "" FORCE)
    set(BUILD_DOC OFF CACHE BOOL "" FORCE)
    set(BUILD_TESTS OFF CACHE BOOL "" FORCE)
    set(SKIP_PORTABILITY_TEST ON CACHE BOOL "" FORCE)

    include(FetchContent)
    FetchContent_Declare(
        cereal
        GIT_REPOSITORY https://github.com/USCiLab/cereal.git
        GIT_TAG        v1.3.2
    )
    FetchContent_MakeAvailable(cereal)
endif()

file(GLOB EDITOR_SOURCES
    "src/*.cpp"
    "src/*.hpp"
)

add_executable(savior_editor ${EDITOR_SOURCES})

target_include_directories(savior_editor PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
)

target_link_libraries(savior_editor PRIVATE
    Qt6::Widgets
    Qt6::Core
    Qt6::Gui
    cereal
)
