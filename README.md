# gengxuexin.github.io

个人作品集站点 —— 面向 AI 应用 / Agent 工程师岗位。

## 内容结构

| 区块 | 内容 |
|------|------|
| Hero | 定位 / 一句话主张 / 联系方式 |
| 01 核心竞争力 | AI+复合背景、工程化与架构能力、质量与风险意识 |
| 02 关于我 | 双学位背景、复合背景如何迁移到 AI 工程 |
| 03 项目 | 消防智能执法多模态 Agent、食品工厂 HACCP 巡检整改闭环、服装门店智能运营助手、食品研发智能决策 |
| 04 怎么做的 | AI 协作四步闭环、验证机制（上下文指纹 / 空跑阻断 / 噪声底 / 事实核对器 / JS 语法门禁）、工具链 |
| 05 工程判断力 | 五个真实案例故事 |
| 06 技术栈 | 六类能力 |
| 07 联系 | 联系方式与三个开源仓库 |

## 本地预览

```bash
python -m http.server 8899 --bind 127.0.0.1
# → http://127.0.0.1:8899
```

> 纯静态站点，无构建步骤。所有资源使用 ASCII 文件名
> （中文文件名在 HTTP 路径下会 404）。

## 自检（改完必跑）

```bash
python -m http.server 8899 --bind 127.0.0.1 &
python -u check_site.py http://127.0.0.1:8899/index.html
```

`check_site.py` 用 CDP 打开真实浏览器，查三个维度：

| 维度 | 查什么 | 为什么不能只 grep 源码 |
|------|--------|----------------------|
| 资源可达 | 每个 `a[href]` / `img[src]` 逐个 fetch 看 HTTP 状态 | grep 只能证明字符串存在 |
| 锚点有效 | 每个 `#anchor` 在 DOM 里真有对应 `id` 元素 | 锚点失效只在渲染后才暴露 |
| **结构完整** | **源码里每个 `id="..."` 必须在渲染后的 DOM 里存在** | **源码正常 ≠ 页面完整** |

第三条是为一个真实 bug 写的：站点里曾出现字面量 `<code><script></code>`，
浏览器从那个裸标签开始把后面所有内容当脚本文本吞掉——
**源码 grep 完全正常**（section 都在），但渲染出来的 DOM 里
「工程判断力 / 技术栈 / 联系」三个区块全部消失，
页面底部只剩一张断掉的表格。

那次发现的关键是：**资源链接全部 200，但页面是残缺的**。
所以「链接都能打开」不等于「页面完整」，必须查 DOM。

这类 bug 的正确写法是 `<code>&lt;script&gt;</code>`。

## 部署

GitHub Pages：Settings → Pages → Source 选 `main` 分支 / 根目录。

## 相关仓库

- [inspection-multi-agent-fire-agents](https://github.com/gengxuexin/inspection-multi-agent-fire-agents)
- [inspection-multi-agent-foodfactory-agents](https://github.com/gengxuexin/inspection-multi-agent-foodfactory-agents)
- [SECOND-DIMENSION_Agents](https://github.com/gengxuexin/SECOND-DIMENSION_Agents)
