#!/usr/bin/env python3

import os
import glob
import shutil
import json

from pico_project import GenerateCMake

boards = ["pico", "pico_w", "pico2", "pico2_w"]

platforms = {
    "pico": ["rp2040"],
    "pico_w": ["rp2040"],
    "pico2": ["rp2350-arm-s", "rp2350-riscv"],
    "pico2_w": ["rp2350-arm-s", "rp2350-riscv"],
}

examples = {
    "example_format": {
        "path": "hello_world/usb",
        "name": "usb",
        "libPaths": [],
        "libNames": [],
        "boards": [],
        "supportRiscV": False,
    }
}

examples.clear()

CURRENT_DATA_VERSION = "0.17.0"

SDK_VERSION = "2.1.1"

try:
    shutil.rmtree("pico-examples")
except FileNotFoundError:
    pass
try:
    for path in glob.glob("errors-pico*"):
        shutil.rmtree(path)
except FileNotFoundError:
    pass
os.system(
    f"git -c advice.detachedHead=false clone https://github.com/raspberrypi/pico-examples.git --depth=1 --branch sdk-{SDK_VERSION}"
)
os.environ["PICO_SDK_PATH"] = f"~/.pico-sdk/sdk/{SDK_VERSION}"
os.environ["WIFI_SSID"] = "Your Wi-Fi SSID"
os.environ["WIFI_PASSWORD"] = "Your Wi-Fi Password"

for board in boards:
    for platform in platforms[board]:
        try:
            shutil.rmtree("build")
        except FileNotFoundError:
            pass
        toolchainVersion = "RISCV_RPI_2_1_1_3" if "riscv" in platform else "14_2_Rel1"
        toolchainPath = f"~/.pico-sdk/toolchain/{toolchainVersion}"
        picotoolDir = f"~/.pico-sdk/picotool/{SDK_VERSION}/picotool"
        os.system(
            f"cmake -S pico-examples -B build -DPICO_BOARD={board} -DPICO_PLATFORM={platform} -DPICO_TOOLCHAIN_PATH={toolchainPath} -Dpicotool_DIR={picotoolDir}"
        )

        os.system("cmake --build build --target help > targets.txt")

        targets = []

        with open("targets.txt", "r") as f:
            for line in f.readlines():
                target = line.strip(".").strip()
                if (
                    "all" in target
                    or "build_variant" in target
                    or target == "clean"
                    or target == "depend"
                    or target == "edit_cache"
                    or target == "rebuild_cache"
                    or target.endswith("_pio_h")
                    or target.endswith("_poll")
                ):
                    continue
                if target.endswith("_background"):
                    target = target[: -len("_background")]
                targets.append(target)

        walk_dir = "./pico-examples"
        target_locs = {}
        lib_locs = {}

        for root, subdirs, files in os.walk(walk_dir):
            for filename in files:
                if filename != "CMakeLists.txt":
                    continue
                file_path = os.path.join(root, filename)

                with open(file_path, "r") as f:
                    f_content = f.read()
                    if "add_library" in f_content:
                        for target in targets:
                            if f"add_library({target}" in f_content:
                                tmp = lib_locs.get(target, {"locs": []})
                                tmp["locs"].append(file_path)
                                lib_locs[target] = tmp
                    if "add_executable" in f_content:
                        exes = []
                        for target in targets:
                            if (
                                f"pico_add_extra_outputs({target})" in f_content
                                or f"pico_add_extra_outputs({target}_background)"
                                in f_content
                            ):
                                exes.append(target)
                                tmp = target_locs.get(target, {"locs": [], "libs": []})
                                tmp["locs"].append(file_path)
                                target_locs[target] = tmp

        for k, v in target_locs.items():
            if len(v["locs"]) > 1:
                raise ValueError(f"Too many locs {v}")
            target_locs[k]["loc"] = v["locs"][0]
            with open(v["locs"][0], "r") as f:
                f_content = f.read()
                for lib in lib_locs:
                    if lib in f_content:
                        target_locs[k]["libs"].append(lib)

        for k, v in lib_locs.items():
            if len(v["locs"]) > 1:
                raise ValueError(f"Too many locs {v}")
            lib_locs[k]["loc"] = v["locs"][0]

        # Test build them all
        try:
            shutil.rmtree("tmp")
            shutil.rmtree("tmp-build")
        except FileNotFoundError:
            pass
        for target, v in target_locs.items():
            os.mkdir("tmp-build")
            loc = v["loc"]
            loc = loc.replace("/CMakeLists.txt", "")
            shutil.copytree(loc, "tmp")
            if len(v["libs"]):
                for lib in v["libs"]:
                    shutil.copytree(
                        lib_locs[lib]["loc"].replace("/CMakeLists.txt", ""),
                        f"tmp/{lib}",
                    )
            params = {
                "projectName": target,
                "wantOverwrite": True,
                "wantConvert": True,
                "wantExample": True,
                "wantThreadsafeBackground": False,
                "wantPoll": False,
                "boardtype": board,
                "sdkVersion": SDK_VERSION,
                "toolchainVersion": toolchainVersion,
                "picotoolVersion": SDK_VERSION,
                "exampleLibs": v["libs"],
            }
            GenerateCMake("tmp", params)
            if params["wantThreadsafeBackground"] or params["wantPoll"]:
                # Write lwipopts for examples
                shutil.copy("lwipopts.h", "tmp/")
            shutil.copy("pico-examples/pico_sdk_import.cmake", "tmp/")

            retcmake = os.system(
                "cmake -S tmp -B tmp-build -DCMAKE_COMPILE_WARNING_AS_ERROR=ON"
            )
            retbuild = os.system("cmake --build tmp-build --parallel 22")
            if retcmake or retbuild:
                print(
                    f"Error occurred with {target} {v} - cmake {retcmake}, build {retbuild}"
                )
                shutil.copytree("tmp", f"errors-{board}-{platform}/{target}")
            else:
                if examples.get(target) != None:
                    example = examples[target]
                    assert example["path"] == loc.replace(f"{walk_dir}/", "")
                    assert example["name"] == target
                    assert example["libPaths"] == [
                        lib_locs[lib]["loc"]
                        .replace("/CMakeLists.txt", "")
                        .replace(f"{walk_dir}/", "")
                        for lib in v["libs"]
                    ]
                    assert example["libNames"] == v["libs"]
                    if not board in example["boards"]:
                        example["boards"].append(board)
                    example["supportRiscV"] |= "riscv" in platform
                else:
                    examples[target] = {
                        "path": loc.replace(f"{walk_dir}/", ""),
                        "name": target,
                        "libPaths": [
                            lib_locs[lib]["loc"]
                            .replace("/CMakeLists.txt", "")
                            .replace(f"{walk_dir}/", "")
                            for lib in v["libs"]
                        ],
                        "libNames": v["libs"],
                        "boards": [board],
                        "supportRiscV": "riscv" in platform,
                    }

            shutil.rmtree("tmp")
            shutil.rmtree("tmp-build")

with open(
    f"{os.path.dirname(os.path.realpath(__file__))}/../data/{CURRENT_DATA_VERSION}/examples.json",
    "w",
) as f:
    json.dump(examples, f, indent=4)
