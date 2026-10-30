#!/usr/bin/env python3
"""Expo 前端代码生成器:React Native 的 Expo 托管工作流变体。

生成产物与裸 RN 完全同构(继承 ReactNativeStackAdapter),差异只在:
- MARKERS:app.config.* 是 Expo 独有标记(裸 RN / Web 工程不会有);
  注意 Expo prebuild 出的 ios/android 目录会同时命中 react_native,
  以 detect evidence 区分;
- DEPLOY 路由走 EAS(eas-build),本地 runner 同样只登记不执行。
命令映射沿用裸 RN:tsc 类型检查为 build 门,jest preset 由项目
package.json(jest-expo)提供,命令本身不变。
"""
from __future__ import annotations

from lib.stack.adapter import register
from lib.stack.react_native.adapter import ReactNativeStackAdapter


@register
class ExpoStackAdapter(ReactNativeStackAdapter):
    name = "expo"
    MARKERS = ["app.config.js", "app.config.ts"]
    DEPLOY = ["eas-build"]
