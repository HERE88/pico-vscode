import { readFileSync } from "fs";
import { Uri } from "vscode";

export interface VersionBundle {
  python: {
    version: string;
    macos: string;
    windowsAmd64: string;
  };
  ninja: string;
  cmake: string;
  toolchain: string;
}

export interface VersionBundles {
  [version: string]: VersionBundle;
}

export default class VersionBundlesLoader {
  private bundles: VersionBundles;

  constructor(extensionUri: Uri) {
    try {
      const bundles = readFileSync(
        Uri.joinPath(
          extensionUri, "data", "0.10.0", "versionBundles.json").fsPath,
        "utf8"
      );
      this.bundles = JSON.parse(bundles) as VersionBundles;
    } catch (e) {
      this.bundles = {};
    }
  }

  public getModuleVersion(version: string): VersionBundle | undefined {
    return this.bundles[version];
  }
}
