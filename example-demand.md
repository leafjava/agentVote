CargoX 商品信用网络 (CCN) 产品需求文档（PRD）
文档信息
●文档版本：V1.0
●更新时间：2025年12月
●适用范围：PicWe 商品信用网络（CCN）全链商品融资与结算平台
●文档状态：草案

一、产品概述
1.1 产品定位
CargoX 商品信用网络（CCN）是一个去中心化、基于区块链的商品融资与结算平台，致力于通过区块链技术和智能合约将传统大宗商品贸易转化为可链上融资和交易的信用资产。通过CommodityAssetRegistry数据确权层，将商品仓单、应收账款、预付款合同等物理世界中的贸易单据转化为可在链上进行融资的资产。平台通过AI风控、跨链结算和智能分润系统，优化全球贸易融资效率，降低融资成本，解决结算缓慢、融资难等问题。
1.2 核心价值主张
对象	核心价值
终端用户	快速、安全的支付体验，支持法币和加密货币支付
AI Agent	支持对话支付功能，推荐产品并获得分润
商户	多渠道销售，简单集成，自动化分润与结算
PicWe平台	提供统一的支付、路由、分润结算系统，确保高效透明

二、系统角色
角色	描述	核心需求
终端用户	发起支付操作、购买商品的消费者	简单、快速、安全的支付体验，支持法币与数字货币支付
AI Agent	发起支付请求、推荐产品并获得分润的智能体	支付能力集成、产品发现与推荐、自动化分润与收入
商户	接入PicWe平台进行商品销售的第三方	多渠道销售、跨链结算、自动化分润与数据分析
PicWe平台	支付中台，负责协议聚合、智能路由与分润结算	高效的支付路由、跨链结算、AI风控、支持多个支付协议的聚合

三、核心功能模块
3.1 支付处理引擎
●多渠道支付聚合：支持法币（USDT、USD等）与数字货币支付（如ETH、USDT等）。
●智能路由系统：基于交易成本、速度、成功率等因素优化支付渠道。
●统一支付API：提供标准化接口和Webhook回调，简化支付集成。
3.2 协议聚合层
●AP2协议支持：集成Agent支付协议，确保智能体的支付能力。
●X402协议支持：集成低成本L2支付协议，提高支付效率。
●ERC8004身份认证系统：支持链上身份验证和凭证。
●插件化架构：支持未来支付协议的扩展。
3.3 商品信用池
●仓单融资池：将仓单进行质押，获得USDT贷款。
●应收账款融资池：将应收账款转化为链上稳定的收益资产。
●预付款融资池：支持供应商接单前的资金垫资。
3.4 分润管理与数据分析
●分润管理系统：智能计算并自动记录分润佣金。
●销售分析看板：展示商品销售情况，提供实时数据分析。
3.5 SDK集成
●商户SDK：用于支付处理、产品发布与管理。
●Agent SDK：集成支付调用与产品销售功能。
●管理后台：管理订单、产品以及销售数据的后台系统。

四、核心业务流程
4.1 Agent内支付流程
1.用户在Agent内选择商品并触发支付。
2.Agent调用CargoX SDK，智能路由选择支付方式。
3.执行支付并返回支付状态回调。
4.Agent展示支付结果。
4.2 商户直接支付流程
1.用户点击商户页面的支付按钮。
2.商户SDK调用PicWe支付接口。
3.支付组件展示并执行支付。
4.支付完成后，PicWe通过Webhook通知商户支付结果。
4.3 商品融资流程
1.商品被注册到CommodityAssetRegistry。
2.商户发起融资请求并选择适合的融资池。
3.用户参与融资，获得基于实际现金流的收益。
4.完成支付后，融资资金进行清算并分润。

五、非功能性需求
类别	要求
性能	单节点并发 > 5,000 TPS，API响应时间 < 500ms
安全	HMAC-SHA256签名、AES256加密、HTTPS全链路
可用性	SLA ≥ 99.5%，支付成功率 > 98%
扩展性	模块化架构，支持新支付渠道的快速接入
兼容性	支持主流AI Agent框架与Web/移动端

六、版本规划
阶段	目标	时间
V1.0	MVP版本：基础支付处理、仓单融资池与应收账款池功能	2025年12月
V1.1	扩展功能：添加预付款融资池、AI风控支持	2026年Q1
V2.0	全链支持：跨链支付与结算，支持多支付协议	2026年Q2

PicWe 商品信用网络 (CCN) 技术设计文档（TDD）
一、项目概述
项目项	内容
项目名称	CargoX 商品信用网络（CCN）— 全球大宗商品链上融资与结算平台
目标	利用区块链技术，将全球大宗商品转化为可投资的链上信用资产，提供实时的支付结算与智能融资解决方案
支持网络	EVM（Ethereum, BSC, Polygon）/ Solana / ICP
技术栈	NestJS + React + TypeScript + Prisma + Solidity + Anchor
部署形态	模块化微服务架构 + 跨链合约集群 + AI Agent 插件接口
二、系统架构总览
+-------------------------------------------------------------+
CargoX Protocol
🌐 Multi-Chain Core Layer
- EVM Payment Router (Solidity)
- Solana Payment Vault (Anchor)
- ICP Canister Gateway (Motoko)
-------------------------------------------------------------
🧩 Aggregation Service Layer
- Smart Router (Tx Orchestration)
- Settlement Engine (AI-based Fee Split)
- Subscription & Recurring Payment Module
- Oracle & Price Feed Integrator
-------------------------------------------------------------
⚙️ Backend Control Layer
- NestJS API Gateway
- Prisma + PostgreSQL
- Redis (Event Queue)
- WebSocket / gRPC
-------------------------------------------------------------
💻 Frontend & SDK Layer
- React Dashboard (Next.js / Vite)
- Multi-chain SDK (TS / Python)
- Plugin SDK (for ChatGPT / Claude / Web Apps)
+-------------------------------------------------------------+

三、核心模块设计
1️⃣ 合约层（Multi-chain Smart Contracts）
●EVM 支持：使用Solidity，框架为Hardhat与OpenZeppelin。
●Solana 支持：使用Anchor框架。
●ICP 支持：使用Motoko。
2️⃣ 后端服务层（NestJS）
●提供REST/gRPC接口，处理交易签名与支付转发。
●结算服务：AI驱动的分润计算与交易对账。
3️⃣ 前端层（React + TypeScript）
●商户控制台、支付组件、AI控制面板、SDK集成等功能。

四、跨链聚合逻辑
●支持Solana、EVM与ICP之间的跨链支付。
●使用Wormhole、Axelar等技术实现跨链通信。
五、安全与合规
●支持多重签名（MPC / Safe multisig）。
●所有交易数据使用AES-256加密，符合FATF VASP标准。
六、部署方案
●支持AWS EKS进行生产环境部署，使用Docker Compose进行开发环境搭建。
七、未来扩展
●支持RWA场景下的链上分账。
●AI自动支付策略学习与账户抽象（ERC-4337）。

总结
CargoX 商品信用网络（CCN）旨在通过区块链技术提升大宗商品贸易融资的效率，解决现有市场中的资金结算慢、融资成本高等问题。通过智能合约、AI风控与跨链结算，CCN为商户、AI Agent和用户提供无缝的支付和分润体验。

