# AW0.81 — hardware scaling / resource profile, fixed 20 PDF

**RESOURCE MODES NOT JUSTIFIED**. Это исследование runtime limits на текущей машине; профили не внедрены.

Измерения завершены: 9 основных прогонов, 2 сравнения порядка, 2 длительных повтора — 13 measured runs на одних и тех же 20 PDF. Каждый завершил 16 TRANSLATED / 4 FAILED_SOURCE_PRESERVED без fatal. Дополнительно выполнены 6 prepared-data GPU microtrials. Это завершение hardware benchmark; качество AW0.81 до релизного уровня здесь не переоценивалось.

Вывод относится к обоснованности внедрения режимов по полученным данным. Единственная конфигурация, совпадающая сама с собой, не доказывает нулевое влияние ресурсов. Неэквивалентный вывод и возможный дрейф ограничивают причинные выводы о масштабировании.

Важные результаты: увеличение CPU с 6 до 14 потоков дало в трёх эквивалентных внутри пары сравнениях +5,61%, −0,58% и −1,73%; устойчивого большого выигрыша не видно. Для LOW GPU увеличение RAM/cache budget с 8 до 24 GiB дало +7,18% и +0,90% в двух эквивалентных парах. Это единичные замеры разных bundles; они не устанавливают универсальную точку насыщения физических CPU/RAM.

В HIGH GPU / LOW RAM прогонах зафиксирован OCR fallback на CPU около job commit cap8 GiB при значительном объёме свободной системной RAM. Тип исходной vendor-ошибки скрыт OCR worker, поэтому точный счётчик OCR OOM недоступен. Ограничение commit приложения и нехватка физической памяти ПК — разные причины. Самые большие сырые выигрыши RAM при HIGH GPU сопровождаются изменённым OCR/translation workload и не принимаются как ускорение с сохранением результата.

Доступный VRAM budget не превращается автоматически в используемую память: фактический пик device VRAM в матрице около 3,4–4,2 GiB, а максимальный NMT batch — 242 source tokens. LOW cap равен384. OCR worker хранит один model key и перезагружает варианты распознавания при переключении. В этой задаче этот код не оптимизировался.

## Hardware и scope

Reference: Ryzen 7 5700X / 8 cores / 16 logical threads; RAM 31.91 GiB; GPU NVIDIA GeForce RTX 3080, 12.00 GiB VRAM, CUDA. Полный исходный snapshot — hardware_summary.json.

Все trials используют AUTOMATIC quality policy: прежние NMT/OCR модели, beam, token/decoding limits, DPI, thresholds, orientation/structure, Knowledge/TM/glossary content, Router, guards, writer и recovery. Меняются только QA resource settings. Это фиксирует параметры качества, но не гарантирует идентичный результат: изменения OCR source/translation отдельно проверены ниже. Старые PerformanceProfile economy/fast/turbo меняют качество, поэтому ими нельзя подменять рекомендуемые resource modes.

CPU — реальные intra_threads/ocr_threads и OMP/MKL/OpenBLAS caps, inter_threads=1; это не Windows process CPU hard quota. RAM — Windows job-wide COMMIT cap, не искусственное выделение RAM и не строгий RSS cap. Job commit peak — lifetime high-water mark, включая исключённый warmup; RSS/private commit sampled только в measured window. Сумма RSS процессов может учитывать shared pages несколько раз. GPU — Paddle worker allocator cap, auto_growth без резервирования; CT2 общего CUDA allocator quota API не предоставляет, aggregate per-process VRAM cap UNAVAILABLE. Budget 10.5 GiB в coexistence arms оставляет 1 GiB номинального headroom для CT2.

Основная GPU utilization/VRAM/температура/clocks/power — device-wide nvidia-smi, включая другие приложения. nvidia-smi per-process WDDM memory unavailable. Дополнительные штатные Windows CIM counters дают per-PID dedicated/shared GPU accounting, busiest compute/3D engine utilization и system hard-fault disk reads. Sidecar добавлен во время run7: первые четыре завершённых trials этих данных не имеют, поэтому основное сравнение использует единый исходный one-second monitor. CPU actual clock/temperature, process-owned SM utilization и queue starvation — UNAVAILABLE. Child CPU time оценён по one-second process-tree samples: небольшое время между последним sample и exit worker может не попасть в сумму.

[Windows memory-limit semantics](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information) · [Paddle allocator strategy](https://www.paddlepaddle.org.cn/documentation/guides/flags/memory_cn.html).

## Методика и fixed sample

20 PDF / 39 source pages, только из run 25825c3f75a7; 5 EASY_NATIVE / 5 MEDIUM / 5 OCR_MIXED / 5 HEAVY_OTHER. Полный метод и SHA в sample_manifest.json. Run order: `['run1', 'run8', 'mid', 'run2', 'run7', 'run3', 'run6', 'run4', 'run5']`. Одинаковый warmup по frozen sample перед каждым run, исключён из measured wall; конфигурации чередуются. Matrix HIGH GPU включает residency/persistence/batch как один bundle, RAM включает commit limit/cache entries: это не изолированный эффект физического объёма памяти.

| # calibration | Bucket | Type | Pages | Member |
|---:|---|---|---:|---|
| 2 | OCR_MIXED | mixed | 2 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022  第七代伊兰特(CN7C) G 1.4 T-GDI 部品检查流程/BJ Boot/部件和部件位置.pdf |
| 11 | EASY_NATIVE | native | 1 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022  第七代伊兰特(CN7C) G 1.4 T-GDI 部品检查流程/Intake Air Temperature Sensor (IATS)/C120102 左前轮速传感器范围 性能 间歇/检验维修.pdf |
| 15 | OCR_MIXED | mixed | 1 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022  第七代伊兰特(CN7C) G 1.4 T-GDI 部品检查流程/Rear Door Belt Outside Weatherstrip/维修程序.pdf |
| 17 | MEDIUM | native | 1 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022  第七代伊兰特(CN7C) G 1.4 T-GDI 部品检查流程/Side Impact Sensor (SIS)/B140900 驾驶席侧面碰撞传感器(SIS)通信故障/故障代码信息和检查.pdf |
| 20 | MEDIUM | native | 1 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022  第七代伊兰特(CN7C) G 1.4 T-GDI 部品检查流程/SRS Control Module (SRSCM)/P203300 废气温度传感器电路电压高，组1传感器2/线束检查.pdf |
| 28 | OCR_MIXED | mixed | 1 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022  第七代伊兰特(CN7C) G 1.5 MPI 部品检查流程/DIS head unit/C110117 蓄电池电压高/故障代码信息和检查.pdf |
| 29 | MEDIUM | native | 1 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022  第七代伊兰特(CN7C) G 1.5 MPI 部品检查流程/DIS head unit/C125901 方向盘转角传感器-电气故障/部件检查.pdf |
| 38 | EASY_NATIVE | native | 1 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022  第七代伊兰特(CN7C) G 1.5 MPI 部品检查流程/Passenger Airbag (PAB) Module/B135500 助手席空气囊电阻电路与蓄电池电路短路(1级)/ETM.pdf |
| 44 | EASY_NATIVE | native | 1 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022 第七代伊兰特(CN7C) G 1.4 T-GDI 故障代码维修指南/ABS ESC/C181483 CAN信息故障 - SAS (CRC)/线束检查.pdf |
| 46 | MEDIUM | native | 1 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022 第七代伊兰特(CN7C) G 1.4 T-GDI 故障代码维修指南/Rear Corner Radar/C166A87 与LDWS LKAS的通信CAN超时/检验维修.pdf |
| 47 | MEDIUM | native | 1 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022 第七代伊兰特(CN7C) G 1.4 T-GDI 故障代码维修指南/中央网关/B252400 右前转向信号电路与搭铁电路短路/故障代码信息和检查.pdf |
| 53 | OCR_MIXED | mixed | 2 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022 第七代伊兰特(CN7C) G 1.4 T-GDI 故障代码维修指南/双离合器变速器/P090412 1档选档传感器对蓄电池短路/线束检查.pdf |
| 55 | EASY_NATIVE | native | 1 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022 第七代伊兰特(CN7C) G 1.4 T-GDI 故障代码维修指南/发动机控制/P013A00 氧传感器响应慢 - 浓到稀组1传感器2/检验维修.pdf |
| 57 | HEAVY_OTHER | image_only | 5 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022 第七代伊兰特(CN7C) G 1.4 T-GDI 故障代码维修指南/发动机控制/P193100 阀持续时间传感器霍尔 角度关联性/示意图.pdf |
| 59 | EASY_NATIVE | native | 1 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022 第七代伊兰特(CN7C) G 1.4 T-GDI 故障代码维修指南/发动机控制/P261000 ECM PCM内部发动机关闭定时器性能/检验维修.pdf |
| 67 | OCR_MIXED | mixed | 2 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022 第七代伊兰特(CN7C) G 1.4 T-GDI 维修手册/DCT (双离合变速器)系统/双离合变速器控制系统/输入速度传感器/维修程序.pdf |
| 77 | HEAVY_OTHER | image_only | 8 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022 第七代伊兰特(CN7C) G 1.5 MPI 故障代码维修指南/中央网关/C161100 与EMS的CAN通信超时/示意图.pdf |
| 83 | HEAVY_OTHER | image_only | 5 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022 第七代伊兰特(CN7C) G 1.5 MPI 故障代码维修指南/发动机控制/P040400 废气再循环控制电路范围 性能/示意图.pdf |
| 94 | HEAVY_OTHER | native | 2 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022 第七代伊兰特(CN7C) G 1.5 MPI 维修手册/发动机电气系统/充电系统/故障检修.pdf |
| 99 | HEAVY_OTHER | image_only | 1 | 2022 第七代伊兰特(CN7C) 维修手册电路图 用户手册/2022 第七代伊兰特(CN7C) 电路图/G 1.4 T-GDI/示意图/车身电气系统/遥控＆防盗警报系统/示意图.pdf |

## Factorial 8 + MID

| Run | CPU / OCR threads | GPU | RAM GiB | Wall s | docs/h | Δ MID % | T / F | EQ |
|---|---|---|---:|---:|---:|---:|---|---|
| run1 | 6 / 6 | LOW 4.5GiB | 8 | 1581.29 | 45.53 | -8.08 | 16 / 4 | FAIL |
| run8 | 14 / 14 | HIGH 10.5GiB | 24 | 1420.32 | 50.69 | 2.34 | 16 / 4 | FAIL |
| mid | 8 / 4 | MID 6.5GiB | 16 | 1453.59 | 49.53 | 0.00 | 16 / 4 | PASS |
| run2 | 14 / 14 | LOW 4.5GiB | 8 | 1497.33 | 48.09 | -2.92 | 16 / 4 | FAIL |
| run7 | 6 / 6 | HIGH 10.5GiB | 24 | 1395.80 | 51.58 | 4.14 | 16 / 4 | FAIL |
| run3 | 6 / 6 | HIGH 10.5GiB | 8 | 1626.23 | 44.27 | -10.62 | 16 / 4 | FAIL |
| run6 | 14 / 14 | LOW 4.5GiB | 24 | 1483.96 | 48.52 | -2.05 | 16 / 4 | FAIL |
| run4 | 6 / 6 | LOW 4.5GiB | 24 | 1475.29 | 48.80 | -1.47 | 16 / 4 | FAIL |
| run5 | 14 / 14 | HIGH 10.5GiB | 8 | 1788.56 | 40.26 | -18.73 | 16 / 4 | FAIL |

## CPU, GPU and RAM resource curves

Each curve row retains its other-factor settings; LOW→HIGH gain is paired at equal other factors. MID changes several controls and is shown as a control, not an isolated midpoint.

| Run | NMT / OCR threads | Fixed GPU / RAM | Wall s | docs/h | CPU avg %machine | Paired CPU gain % |
|---|---|---|---:|---:|---:|---:|
| run1 | 6 / 6 | LOW / 8GiB | 1581.29 | 45.53 | 7.94 | UNAVAILABLE |
| run8 | 14 / 14 | HIGH / 24GiB | 1420.32 | 50.69 | 8.70 | -1.73 |
| mid | 8 / 4 | MID / 16GiB | 1453.59 | 49.53 | 8.11 | UNAVAILABLE |
| run2 | 14 / 14 | LOW / 8GiB | 1497.33 | 48.09 | 8.35 | 5.61 |
| run7 | 6 / 6 | HIGH / 24GiB | 1395.80 | 51.58 | 8.21 | UNAVAILABLE |
| run3 | 6 / 6 | HIGH / 8GiB | 1626.23 | 44.27 | 12.21 | UNAVAILABLE |
| run6 | 14 / 14 | LOW / 24GiB | 1483.96 | 48.52 | 8.40 | -0.58 |
| run4 | 6 / 6 | LOW / 24GiB | 1475.29 | 48.80 | 8.00 | UNAVAILABLE |
| run5 | 14 / 14 | HIGH / 8GiB | 1788.56 | 40.26 | 16.86 | -9.08 |

| Run | GPU budget / observed device peak GiB | OCR batch / NMT token budget | Wall s | docs/h | GPU avg %device | Paired GPU gain % |
|---|---|---|---:|---:|---:|---:|
| run1 | 4.5 / 3.48 | 2 / 384 | 1581.29 | 45.53 | 34.04 | UNAVAILABLE |
| run8 | 10.5 / 4.24 | 16 / 1536 | 1420.32 | 50.69 | 24.08 | 4.48 |
| mid | 6.5 / 3.45 | 6 / 768 | 1453.59 | 49.53 | 20.90 | UNAVAILABLE |
| run2 | 4.5 / 3.45 | 2 / 384 | 1497.33 | 48.09 | 20.60 | UNAVAILABLE |
| run7 | 10.5 / 4.22 | 16 / 1536 | 1395.80 | 51.58 | 21.24 | 5.70 |
| run3 | 10.5 / 4.21 | 16 / 1536 | 1626.23 | 44.27 | 19.67 | -2.76 |
| run6 | 4.5 / 3.45 | 2 / 384 | 1483.96 | 48.52 | 19.84 | UNAVAILABLE |
| run4 | 4.5 / 3.45 | 2 / 384 | 1475.29 | 48.80 | 21.66 | UNAVAILABLE |
| run5 | 10.5 / 4.20 | 16 / 1536 | 1788.56 | 40.26 | 17.57 | -16.28 |

| Run | RAM commit cap GiB / observed RSS peak GiB | Cache cap / entries | Wall s | docs/h | Cache hits / misses | Paired RAM gain % |
|---|---|---|---:|---:|---|---:|
| run1 | 8 / 3.22 | 512 / 512 | 1581.29 | 45.53 | 7959 / 1514 | UNAVAILABLE |
| run8 | 24 / 4.16 | 4096 / 1514 | 1420.32 | 50.69 | 7920 / 1513 | 25.93 |
| mid | 16 / 3.13 | 512 / 512 | 1453.59 | 49.53 | 7957 / 1516 | UNAVAILABLE |
| run2 | 8 / 3.41 | 512 / 512 | 1497.33 | 48.09 | 7959 / 1514 | UNAVAILABLE |
| run7 | 24 / 4.15 | 4096 / 1514 | 1395.80 | 51.58 | 7920 / 1513 | 16.51 |
| run3 | 8 / 3.92 | 512 / 512 | 1626.23 | 44.27 | 7913 / 1520 | UNAVAILABLE |
| run6 | 24 / 3.34 | 4096 / 1508 | 1483.96 | 48.52 | 7966 / 1507 | 0.90 |
| run4 | 24 / 3.11 | 4096 / 1508 | 1475.29 | 48.80 | 7966 / 1507 | 7.18 |
| run5 | 8 / 3.45 | 512 / 512 | 1788.56 | 40.26 | 7913 / 1520 | UNAVAILABLE |

## Curves: conditional CPU/GPU/RAM comparisons

| Factor | LOW → HIGH runs | Throughput Δ % | Wall Δ s | CPU avg Δ points | RSS Δ GiB | Device VRAM Δ MiB | Class | Pair EQ / MID eligible |
|---|---|---:|---:|---:|---:|---:|---|---|
| cpu | run1 → run2 | 5.61 | -83.96 | 0.41 | 0.19 | -32.00 | weak | PASS / False |
| cpu | run3 → run5 | -9.08 | 162.33 | 4.66 | -0.47 | -11.00 | regression | FAIL / False |
| cpu | run4 → run6 | -0.58 | 8.67 | 0.40 | 0.23 | -2.00 | practical saturation/no demonstrated gain | PASS / False |
| cpu | run7 → run8 | -1.73 | 24.52 | 0.48 | 0.01 | 21.00 | practical saturation/no demonstrated gain | PASS / False |
| gpu | run1 → run3 | -2.76 | 44.94 | 4.26 | 0.70 | 745.00 | practical saturation/no demonstrated gain | FAIL / False |
| gpu | run2 → run5 | -16.28 | 291.23 | 8.51 | 0.04 | 766.00 | regression | FAIL / False |
| gpu | run4 → run7 | 5.70 | -79.50 | 0.21 | 1.04 | 789.00 | weak | FAIL / False |
| gpu | run6 → run8 | 4.48 | -63.64 | 0.30 | 0.82 | 812.00 | weak | FAIL / False |
| ram | run1 → run4 | 7.18 | -106.00 | 0.06 | -0.11 | -38.00 | noticeable | PASS / False |
| ram | run2 → run6 | 0.90 | -13.37 | 0.05 | -0.07 | -8.00 | practical saturation/no demonstrated gain | PASS / False |
| ram | run3 → run7 | 16.51 | -230.43 | -3.99 | 0.23 | 6.00 | strong | FAIL / False |
| ram | run5 → run8 | 25.93 | -368.24 | -8.16 | 0.71 | 38.00 | strong | FAIL / False |

Pairwise invariant conditional main effects: `{}`. Pair EQ only establishes invariance between that pair at fixed other-factor settings; a variant may still differ from current MID and remain ineligible for recommendation.

**Raw contrasts: output equivalence FAIL.** Эти значения приведены для полноты матрицы, но смешивают resource changes и изменённую OCR/translation workload. Они не доказывают ускорение с сохранением вывода.
| Main factor | Raw throughput Δ % | Class |
|---|---:|---|
| cpu | -1.58 | practical saturation/no demonstrated gain |
| gpu | -2.63 | practical saturation/no demonstrated gain |
| ram | 12.23 | noticeable |

| Interaction | Raw ratio-of-ratios Δ % |
|---|---:|
| cpuxgpu | -7.75 |
| cpuxram | 0.87 |
| gpuxram | 16.47 |
| cpuxgpuxram | 14.81 |

Factorial status: **COMPLETE_TRIALS_OUTPUT_NON_EQUIVALENT**. Main effects: `{}`. CPU×GPU / CPU×RAM / GPU×RAM / three-way: `{}`. Main effects use geometric HIGH/LOW throughput; interactions are log-throughput ratio-of-ratios contrasts. Ineligible/non-equivalent runs cannot establish a speed winner.

The <3 / 3–7 / 7–15 / >15% bands describe measured differences, not statistical proof of a universal hardware knee. CPU6/14 and memory low/high give only two endpoints. An inactive cap does not locate a physical resource knee. MID changes multiple budgets and is not an isolated CPU curve point.

## Utilization, latency and milestones

| Run | CPU avg/peak %machine | CPU seconds | RSS peak GiB | Job lifetime commit peak GiB | Available min GiB | Cache hit/miss | GPU avg/peak %device | VRAM peak MiB | GPU temp peak C |
|---|---|---:|---:|---:|---:|---|---|---:|---:|
| best_easy_first | 8.10/43.49 | 1884.45 | 3.42 | 6.88 | 17.72 | 7959/1514 | 20.61/100.00 | 3499.00 | 63.00 |
| best_repeat_original | 8.12/51.13 | 1887.73 | 3.19 | 6.74 | 17.83 | 7957/1516 | 19.83/100.00 | 3525.00 | 63.00 |
| mid | 8.11/45.53 | 1887.64 | 3.13 | 6.57 | 18.30 | 7957/1516 | 20.90/100.00 | 3533.00 | 63.00 |
| mid_sustained | 8.11/45.38 | 1893.58 | 3.33 | 7.09 | 17.82 | 7960/1513 | 20.09/100.00 | 3679.00 | 63.00 |
| run1 | 7.94/37.79 | 2009.34 | 3.22 | 6.35 | 17.96 | 7959/1514 | 34.04/100.00 | 3568.00 | 63.00 |
| run2 | 8.35/82.59 | 2001.75 | 3.41 | 7.40 | 17.57 | 7959/1514 | 20.60/100.00 | 3536.00 | 63.00 |
| run3 | 12.21/38.64 | 3177.75 | 3.92 | 8.10 | 17.20 | 7913/1520 | 19.67/100.00 | 4313.00 | 62.00 |
| run4 | 8.00/36.20 | 1889.67 | 3.11 | 6.41 | 17.86 | 7966/1507 | 21.66/100.00 | 3530.00 | 62.00 |
| run5 | 16.86/84.09 | 4828.56 | 3.45 | 8.06 | 17.68 | 7913/1520 | 17.57/100.00 | 4302.00 | 63.00 |
| run6 | 8.40/70.18 | 1995.77 | 3.34 | 7.29 | 17.77 | 7966/1507 | 19.84/100.00 | 3528.00 | 62.00 |
| run7 | 8.21/34.56 | 1834.50 | 4.15 | 8.16 | 17.10 | 7920/1513 | 21.24/100.00 | 4319.00 | 63.00 |
| run7_sustained | 8.28/34.64 | 1774.59 | 4.49 | 8.50 | 16.75 | 9433/0 | 22.41/100.00 | 4335.00 | 63.00 |
| run8 | 8.70/83.09 | 1977.48 | 4.16 | 8.95 | 17.39 | 7920/1513 | 24.08/100.00 | 4340.00 | 62.00 |

| Run | CPU idle samples (~s) | Device GPU idle samples (~s) | GPU clock avg / min MHz | Device power peak W | OCR successful GPU / CPU calls |
|---|---:|---:|---|---:|---|
| best_easy_first | 9 | 303 | 570.44/210.00 | 131.10 | 58/0 |
| best_repeat_original | 11 | 329 | 569.90/210.00 | 130.04 | 58/0 |
| mid | 15 | 334 | 573.81/210.00 | 129.30 | 58/0 |
| mid_sustained | 10 | 314 | 574.69/210.00 | 130.57 | 58/0 |
| run1 | 35 | 0 | 767.06/270.00 | 136.51 | 58/0 |
| run2 | 23 | 303 | 571.82/210.00 | 128.57 | 58/0 |
| run3 | 3 | 235 | 473.55/210.00 | 115.18 | 56/2 |
| run4 | 8 | 300 | 573.96/210.00 | 128.15 | 58/0 |
| run5 | 7 | 272 | 459.36/210.00 | 123.92 | 52/6 |
| run6 | 12 | 337 | 579.16/210.00 | 127.92 | 58/0 |
| run7 | 2 | 241 | 510.47/210.00 | 130.70 | 58/0 |
| run7_sustained | 1 | 209 | 508.49/210.00 | 129.24 | 58/0 |
| run8 | 3 | 197 | 557.10/210.00 | 129.50 | 58/0 |

Периоды idle оцениваются по числу секундных samples: CPU ниже 5%, GPU не выше 3%; это приближение, а не точное непрерывное время. GPU counters относятся ко всей видеокарте. Низкая частота GPU во время простоя не доказывает thermal throttling. Независимой очереди подготовленных документов нет: queue starvation недоступен. Фактические устройства NMT по backend и успешные OCR вызовы сохранены в runs.jsonl.

| Run | pages/h | segments/s | Median/P90/P95 s | First start / processed / translated s | 25/50/75/100% processed s |
|---|---:|---:|---|---|---|
| best_easy_first | 96.69 | 2.96 | 27.17 / 279.41 / 292.05 | 1.22/3.81/3.81 | 24.64 / 111.17 / 428.55 / 1451.96 |
| best_repeat_original | 96.63 | 2.95 | 27.27 / 277.19 / 291.79 | 1.20/72.09/76.69 | 149.54 / 229.19 / 635.73 / 1452.89 |
| mid | 96.59 | 2.95 | 26.94 / 278.88 / 292.50 | 1.24/72.14/76.88 | 149.02 / 228.79 / 635.14 / 1453.46 |
| mid_sustained | 96.23 | 2.94 | 27.20 / 279.65 / 291.60 | 0.13/71.24/75.99 | 149.25 / 229.86 / 635.63 / 1458.90 |
| run1 | 88.79 | 2.71 | 32.85 / 307.03 / 313.14 | 2.19/86.61/91.56 | 176.84 / 261.42 / 695.44 / 1581.15 |
| run2 | 93.77 | 2.87 | 27.36 / 288.62 / 301.41 | 1.23/72.46/77.28 | 150.83 / 231.11 / 648.18 / 1497.19 |
| run3 | 86.33 | 2.64 | 23.79 / 283.45 / 303.67 | 1.20/65.33/70.08 | 135.82 / 209.11 / 599.09 / 1626.10 |
| run4 | 95.17 | 2.91 | 27.20 / 286.49 / 299.30 | 1.19/72.54/77.20 | 150.36 / 229.51 / 642.67 / 1475.16 |
| run5 | 78.50 | 2.40 | 23.96 / 294.75 / 371.77 | 1.22/66.60/71.34 | 137.75 / 211.64 / 904.88 / 1788.43 |
| run6 | 94.61 | 2.89 | 27.45 / 286.79 / 301.41 | 1.20/71.87/76.66 | 150.43 / 231.02 / 647.64 / 1483.82 |
| run7 | 100.59 | 3.07 | 23.91 / 270.92 / 284.84 | 2.58/67.66/72.36 | 138.26 / 211.60 / 603.83 / 1395.66 |
| run7_sustained | 104.82 | 3.20 | 22.51 / 259.85 / 272.47 | 0.13/63.09/67.16 | 128.77 / 197.40 / 570.99 / 1339.31 |
| run8 | 98.85 | 3.02 | 25.35 / 273.46 / 283.40 | 1.23/68.37/73.33 | 143.29 / 220.19 / 621.47 / 1420.19 |

## Model loads, actual batching and failures

| Run | NMT model loads / s | OCR loads >10ms / load s / inference s | Actual max NMT sequences/tokens | NMT failed attempts / fallback | Recorded NMT OOM |
|---|---|---|---|---|---|
| best_easy_first | 27 / 10.29 | 58 / 658.00 / 147.95 | 2/242 | 46 / 45 | 0 |
| best_repeat_original | 28 / 11.01 | 58 / 657.94 / 149.09 | 2/242 | 46 / 45 | 0 |
| mid | 28 / 10.56 | 58 / 657.46 / 148.85 | 2/242 | 46 / 45 | 0 |
| mid_sustained | 28 / 10.85 | 58 / 660.29 / 147.72 | 2/242 | 46 / 45 | 0 |
| run1 | 28 / 10.66 | 58 / 693.17 / 181.26 | 2/242 | 46 / 45 | 0 |
| run2 | 28 / 11.27 | 58 / 661.85 / 172.07 | 2/242 | 46 / 45 | 0 |
| run3 | 4 / 1.69 | 58 / 648.36 / 368.34 | 2/242 | 46 / 45 | 0 |
| run4 | 28 / 11.20 | 58 / 657.37 / 172.11 | 2/242 | 46 / 45 | 0 |
| run5 | 4 / 1.70 | 58 / 608.13 / 521.11 | 2/242 | 46 / 45 | 0 |
| run6 | 28 / 11.32 | 58 / 660.63 / 171.15 | 2/242 | 46 / 45 | 0 |
| run7 | 4 / 1.61 | 58 / 664.01 / 143.32 | 2/242 | 46 / 45 | 0 |
| run7_sustained | 2 / 1.26 | 58 / 655.12 / 141.13 | 2/242 | 46 / 45 | 0 |
| run8 | 4 / 1.61 | 58 / 677.19 / 144.69 | 2/242 | 46 / 45 | 0 |

NMT failed attempts include TranslationError/guards and must not all be interpreted as CUDA allocation failures. OCR vendor exception types are masked by the isolated worker; precise OCR OOM count is UNAVAILABLE. Successful OCR device counts, error-type counts and inclusive stage calls retained in runs.jsonl.

The OCR worker has one cached model key. Auto alternates recognition candidates; switching recognizer invalidates that cache. Thus persistent process residency does not retain both OCR variants, and substantial model loading can remain despite extra nominal VRAM. This behavior was measured and inspected, not optimized in this task.

## Supplementary Windows counters

| Run | Samples / capture span % | Owned dedicated GPU peak GiB | Busiest owned engine avg/peak % | System page reads avg/s | System pages input/output peak/s |
|---|---|---:|---|---:|---|
| best_easy_first | 37 / 52.05 | 2.20 | 33.41/96.00 | 16.03 | 777.00/0.00 |
| best_repeat_original | 69 / 98.14 | 2.21 | 39.48/96.00 | 21.38 | 548.00/0.00 |
| mid | 0 / UNAVAILABLE | UNAVAILABLE | UNAVAILABLE/UNAVAILABLE | UNAVAILABLE | UNAVAILABLE/UNAVAILABLE |
| mid_sustained | 69 / 97.72 | 2.38 | 45.68/100.00 | 22.38 | 566.00/0.00 |
| run1 | 0 / UNAVAILABLE | UNAVAILABLE | UNAVAILABLE/UNAVAILABLE | UNAVAILABLE | UNAVAILABLE/UNAVAILABLE |
| run2 | 0 / UNAVAILABLE | UNAVAILABLE | UNAVAILABLE/UNAVAILABLE | UNAVAILABLE | UNAVAILABLE/UNAVAILABLE |
| run3 | 78 / 99.22 | 2.87 | 38.29/101.00 | 11.09 | 549.00/0.00 |
| run4 | 71 / 99.50 | 2.21 | 47.72/97.00 | 16.70 | 601.00/0.00 |
| run5 | 86 / 99.64 | 2.89 | 28.72/95.00 | 15.79 | 573.00/0.00 |
| run6 | 71 / 98.95 | 2.19 | 42.03/99.00 | 17.92 | 775.00/0.00 |
| run7 | 15 / 21.12 | 2.29 | 37.07/96.00 | 37.60 | 586.00/0.00 |
| run7_sustained | 65 / 100.00 | 3.00 | 38.51/98.00 | 22.29 | 843.00/0.00 |
| run8 | 0 / UNAVAILABLE | UNAVAILABLE | UNAVAILABLE/UNAVAILABLE | UNAVAILABLE | UNAVAILABLE/UNAVAILABLE |

~20s supplemental samples may miss short bursts and do not replace the consistent one-second primary traces. Capture span is the first-to-last query interval, not continuous coverage. Run7 and easy-first have partial late capture; do not compare their supplemental averages as full-run means. WDDM per-PID accounting is not a model-tensor-only allocator footprint. System hard-fault disk reads include executable/file-backed pages and do not prove pagefile pressure or attribute paging to TreeTranslate. No CPU sensor namespace found; no monitoring package installed.

Milestones count processed PDFs including FAILED_SOURCE_PRESERVED, not 20 successful translations. Segments/s counts all processed segments including protected/noise segments; it is not semantic-only inference throughput. Final archive publication occurs after member20; total wall includes final archive validation/publish. Warmup, fingerprint/render inspection and report generation are excluded.

## Equivalence / scheduler / sustained / overlap

Сравнение включает status, полный candidate text и protected IDs/numbers, source-preserved segments, writer result, страницы и нормализованные PDF objects, RGB hashes первого/последнего листа четырёх фиксированных представителей, exact bytes/path failed originals. Округление геометрии objects — 1e-5 points. Это проверка идентичности результата, а не новая оценка его предметного качества.

| Run | Reference | EQ | Documents with differences | Different evidence records |
|---|---|---|---:|---:|
| best_easy_first | mid | PASS | 0 | 0 |
| best_repeat_original | mid | PASS | 0 | 0 |
| mid | mid | PASS | 0 | 0 |
| mid_sustained | mid | PASS | 0 | 0 |
| run1 | mid | FAIL | 2 | 4 |
| run2 | mid | FAIL | 2 | 4 |
| run3 | mid | FAIL | 3 | 7 |
| run4 | mid | FAIL | 2 | 4 |
| run5 | mid | FAIL | 3 | 7 |
| run6 | mid | FAIL | 2 | 4 |
| run7 | mid | FAIL | 3 | 7 |
| run7_sustained | mid | FAIL | 3 | 7 |
| run8 | mid | FAIL | 3 | 7 |

| Rejected run | Candidate-different PDFs | Source-string-different PDFs | Profiler-different PDFs | Changed targets for identical source strings |
|---|---:|---:|---:|---:|
| run1 | 2 | 2 | 0 | 0 |
| run2 | 2 | 2 | 0 | 0 |
| run3 | 3 | 3 | 2 | 22 |
| run4 | 2 | 2 | 0 | 0 |
| run5 | 3 | 3 | 2 | 24 |
| run6 | 2 | 2 | 0 | 0 |
| run7 | 3 | 3 | 2 | 24 |
| run7_sustained | 3 | 3 | 2 | 24 |
| run8 | 3 | 3 | 2 | 24 |

Изменения распознанного исходного текста могут изменить существующий document profile и выбор терминов даже при неизменных моделях, Knowledge и правилах. Конфигурации проверялись как bundles; причинность одного параметра для каждого различия не установлена. Примеры строк и изменённые profiles сохранены в [equivalence_diagnostics.json](C:/TreeTranslate/qa/aw081/hardware_scaling_20/equivalence_diagnostics.json). Предметные переводы в этой задаче не исправлялись.

**Easy-first** на `mid`: throughput Δ 0.06%, eligible True; cheap metadata sort 0.000017s.

| Order | 25 / 50 / 75 / 100% processed s | First / 5 / 10 / 15 / 20 translations ready s |
|---|---|---|
| best_repeat_original | 149.54 / 229.19 / 635.73 / 1452.89 | 76.69 / 214.97 / 339.46 / 1400.19 / UNAVAILABLE |
| best_easy_first | 24.64 / 111.17 / 428.55 / 1451.96 | 3.81 / 24.64 / 129.42 / 720.53 / UNAVAILABLE |

Only iteration order changed; original inventory/context sampling/path reservation preserved. Metadata from frozen sample source inspection, no new OCR/model/profiler for sorting. Early readiness is member-packaging time, not a separately published archive.

Easy-first ускоряет ранний прогресс, но практически не меняет общий wall. В этих trials первый переведённый PDF упакован через 76,69s в original order и 3,81s в easy-first. Это внутренняя готовность member; выходной ZIP публикуется целиком в конце.

Этот scheduler experiment переиспользует metadata, уже собранную для 100-PDF sample. Для полного ZIP наличие page/native/raster metadata до обработки не доказано; archive inventory сразу даёт размеры и пути. Новый глобальный OCR/profiler/native pre-scan для сортировки не предлагается: запуск первого документа должен оставаться быстрым.

QA initialization incident: the initial easy-first AST selector matched both the processing loop and directory-finalization loop and stopped before scan/warmup/DocumentJob. The failed initialization record is preserved in initialization_failures. A separate scheduler adapter selects only the loop constructing DocumentJob; its AST-only preflight passed. Frozen matrix runtime/support scripts and production code were not edited. This is not a failed measured resource trial.

Only one main configuration passed MID equivalence. The second sustained trial diagnoses the fastest rejected configuration; it is not a speed winner or mode recommendation.

**Sustained / thermal / drift**

| Config | Cold / warm wall s | Warm throughput Δ % | Peak GPU temp cold / warm C | Warm active clock median MHz | Warm RSS peak GiB | EQ vs own cold / vs MID / eligible |
|---|---|---:|---|---:|---:|---|
| run7 | 1395.80 / 1339.41 | 4.21 | 63.00 / 63.00 | 780.00 | 4.49 | PASS / FAIL / False |
| mid | 1453.59 / 1459.03 | -0.37 | 63.00 / 63.00 | 780.00 | 3.33 | PASS / PASS / True |

Original-order repeat drift versus its main trial: 0.04%. Each sustained trial first executes the same full20 as excluded warmup in the same process, then measures the fixed20 again. Top2 interleaved in reverse order. Device clocks at low utilization must not be interpreted as thermal throttling. One warm repetition per configuration; no statistical confidence interval. CPU thermal and per-process pagefile attribution unavailable. Supplemental system hard-fault counters are available for captured windows. Device telemetry includes ambient GPU workloads; full20 warmup also retains caches for duplicated inputs.

The full20 warmup also retains lookup caches for the same repeated inputs. Warm/cold speed differences can include cache reuse and filesystem/model warmup, not only thermal or worker effects. They are not used as a full-corpus hardware scaling coefficient. Compare measured cache hits/misses and model-load counts in the utilization tables before attributing a change to heat.

**Prepared-data GPU overlap**: COMPLETE; exact equivalence True; median parallel throughput Δ 3.05%; safe useful concurrent requests False. Estimated overlapping native inference calls: 0.00s.

| Trial | Parallel | Wall s | Exact OCR / NMT |
|---|---|---:|---|
| 1 | False | 28.16 | True / True |
| 2 | True | 26.72 | True / True |
| 3 | True | 26.79 | True / True |
| 4 | False | 27.54 | True / True |
| 5 | False | 27.41 | True / True |
| 6 | True | 26.44 | True / True |

| Residency snapshot | Device VRAM MiB | Owned WDDM dedicated GiB | Owned WDDM shared GiB |
|---|---:|---:|---:|
| idle_before | 1241.00 | 0.00 | 0.00 |
| m2m100_isolated | 1992.00 | 0.73 | 0.07 |
| m2m100_released | 1448.00 | 0.20 | 0.07 |
| argos_isolated | 1863.00 | 0.59 | 0.07 |
| argos_released | 1478.00 | 0.22 | 0.07 |
| ocr_isolated | 2723.00 | 1.45 | 0.15 |
| combined_resident | 3643.00 | 2.34 | 0.15 |

Observed device peak 3838.00MiB; within HIGH budget: True. This is observed fit on the prepared sample, not a worst-case guarantee or aggregate CUDA cap.

На подготовленном workload совместная residency поместилась в budget, но полезного большого выигрыша не показала. Параллельные requests дали слабый эффект; пересечение оценённых native inference intervals не обнаружено. Это не доказывает невозможность другого overlap и не даёт коэффициент ускорения полного pipeline.

Isolated and combined device VRAM snapshots and Paddle allocator measurements: [residency_overlap_probe.json](C:/TreeTranslate/qa/aw081/hardware_scaling_20/residency_overlap_probe.json).
Prepared image/text only; first sample page rendered at scale1.25, not a worst-case full200DPI document footprint. No extraction/writer/archive concurrency or full-pipeline speed claim. OCR native inference interval estimated backwards from RPC completion and worker duration; includes small IPC/serialization error. Overlapping native calls does not prove simultaneous GPU kernels without device tracing. Device-wide VRAM deltas include ambient applications; supplemental Windows per-PID dedicated/shared GPU accounting is captured separately when available. Argos pivot is a diagnostic resource probe, not a changed production route.

**Optional saturation sweep**: NO_ADDITIONAL_SWEEP_JUSTIFIED; 0 additional runs, maximum4. Two endpoints alone do not establish a universal hardware knee; cap binding is an observed operational criterion, not proof of a causal hardware bottleneck.

| Factor | Strong valid effect | Binding among equivalent HIGH arms |
|---|---|---|
| cpu | False | False |
| gpu | False | False |
| ram | False | False |

Sweep decisions require output-equivalent HIGH-arm evidence. An empty eligible HIGH set does not prove that the hardware itself is saturated.

Текущий production pipeline последовательный, GPU queue depth=1. PDF_LOCK охватывает extraction/recognition и writer operations; RuntimeManager сериализует NMT-вызовы своим lock. Совместное присутствие моделей в памяти не означает одновременный inference. GPU microprobe использует только уже подготовленные image/text, без параллельного writer и изменения extraction architecture.

| Stage | Observed scheduling / overlap limit |
|---|---|
| ZIP inventory / path reservation | Выполняется до цикла документов; независимой ready-document queue нет. |
| CPU extraction / OCR preparation | PDF_LOCK сохраняется во время соответствующей операции; overlapping extraction следующего PDF не измерялся. |
| GPU OCR + GPU NMT | В обычном document pipeline перекрытия не наблюдалось; prepared-data probe отдельно проверяет coexistence и concurrent requests. |
| Knowledge / glossary / NMT | Выполняются внутри текущего document/segment flow; отдельная очередь подготовки не реализована и не проверялась. |
| CPU PDF writer | Защищён PDF_LOCK; параллельные небезопасные writer operations не запускались. |
| Archive append / validation / publish | Один владелец выходного ZIP, последовательное добавление; отдельные ранние PDF пользователю не публикуются. |

Основание: [PdfDocument / PDF_LOCK](C:/TreeTranslate/app/documents/pdf_document.py:141), [ArchiveJob processing loop](C:/TreeTranslate/app/documents/archive_job.py:203), [RuntimeManager lock](C:/TreeTranslate/app/engine/runtime/runtime_manager.py:71). Эти ограничения описывают текущую архитектуру; новый scheduler или pipeline в этой задаче не создавался.

## Resource-only candidates and full ZIP estimate

| Mode | Measured config | CPU/OCR threads | RAM cap GiB | GPU budget GiB | Pipeline depth | Sample docs/h | Full hours | Days | PC responsiveness |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| ECO | mid | 8/4 | 16 | 6.5 | 1 | 49.53 | 229.51 | 9.56 | Не измерялась; загрузка ресурсов — только косвенный показатель |
| BALANCED | mid | 8/4 | 16 | 6.5 | 1 | 49.53 | 229.51 | 9.56 | Не измерялась; загрузка ресурсов — только косвенный показатель |
| HIGH | mid | 8/4 | 16 | 6.5 | 1 | 49.53 | 229.51 | 9.56 | Не измерялась; загрузка ресурсов — только косвенный показатель |
| ULTRA | mid | 8/4 | 16 | 6.5 | 1 | 49.53 | 229.51 | 9.56 | Не измерялась; загрузка ресурсов — только косвенный показатель |

Конфигурации, совпавшие с текущим MID: `['mid']`. Четыре строки выше сводятся к одному контрольному набору настроек; они не представляют четыре доказанных режима. Рекомендация — сохранить текущие настройки, без новых ECO/HIGH/ULTRA. Другие варианты не прошли сравнение вывода с MID.

MID repeat reproducibility: **PASS**. Self-equivalence of the reference does not alone validate repeat stability. A NOT_ESTABLISHED result strengthens the reason to retain current settings without promoting a faster variant.

Прогноз по прежней 100-PDF corpus model: 229.51 часа / 9.56 суток; оптимистичный–консервативный сценарий188,23–303,93h (не доверительный интервал). Hardware coefficient = throughput эквивалентной fixed20 конфигурации / throughput MID fixed20; прогноз = corpus hours / coefficient. Нового эквивалентного ускорителя не найдено, поэтому коэффициент1 и прогноз сохранён. 20 PDF намеренно содержат много тяжёлой работы и не используются как самостоятельная модель всего корпуса. Прогноз считает обработку с FAILED_SOURCE_PRESERVED и не гарантирует успешный перевод всех17211 PDF.

Дополнительный выигрыш Ultra относительно более экономного варианта в пределах3% максимума: UNAVAILABLE. Сравнение разных одобренных уровней недоступно: есть только MID. Лишняя RAM/VRAM искусственно не выделялась. Отзывчивость UI не измерялась.

For future machines detect CPU count, available RAM and CUDA/VRAM first, retain OS headroom and choose only measured useful resource ceilings. Do not copy Ryzen5700X/RTX3080 constants into production. Preserve original semantic/quality settings and OOM/fallback/recovery behavior. Four distinct useful performance levels are not established merely by naming four presets.

## Evidence and STOP

[Sample manifest](C:/TreeTranslate/qa/aw081/hardware_scaling_20/sample_manifest.json) · [Runs](C:/TreeTranslate/qa/aw081/hardware_scaling_20/runs.jsonl) · [Factorial](C:/TreeTranslate/qa/aw081/hardware_scaling_20/factorial_analysis.json) · [Recommendations](C:/TreeTranslate/qa/aw081/hardware_scaling_20/mode_recommendations.json).

experiment_manifest.json, hardware_summary.json, resource_samples.jsonl and per-run execution/log/candidate/writer/fingerprint files retained. No heavy monitoring frameworks installed.

[Финальный аудит](C:/TreeTranslate/qa/aw081/hardware_scaling_20/final_evidence_audit.json): CRC, ровно20 файлов PDF в каждом output (отдельно45 directory entries), одинаковые directory paths, точное сохранение failed originals, пустая QA TM, неизменность248 production-файлов и двух frozen QA core scripts. Operational audit не принимает качество отклонённых конфигураций.

**STOP.** Полный17211-PDF прогон не запускался. Production defaults, модели, Knowledge и quality policy не менялись; режимы, UI и scheduler не внедрялись. OCR/glossary не оптимизировались. PHASE B/C, Frozen B, AW0.82 и commit не выполнялись.
