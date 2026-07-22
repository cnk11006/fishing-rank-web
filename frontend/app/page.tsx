"use client";

import Image from "next/image";
import { FormEvent, useEffect, useState } from "react";
import {
  ApiError,
  getAuthenticationStatus,
  loginWithPassword,
  logoutSession,
  searchRank,
  saveSelectedRankItems,
  getMonitoringList,
  addMonitoringItem,
  deleteMonitoringItems,
  collectMonitoringRanks,
  getMonitoringHistory,
  analyzeKeywords,
  getAdvertisingOverview,
  analyzeSeason,
  analyzeCrossPurchase,
  analyzeCandidates,
  getDataManagementOverview,
  migrateLegacyRankSheets,
  clearApplicationCaches,
} from "@/lib/api";
import type {
  RankSearchResponse,
  RankSearchItem,
  SaveSelectedRankResponse,
  MonitorItem,
  MonitoringCollectResponse,
  MonitoringHistoryItem,
  KeywordAnalysisResponse,
  AdvertisingOverviewResponse,
  SeasonAnalysisResponse,
  CrossPurchaseResponse,
  CandidateAnalysisResponse,
  DataManagementOverview,
  RankMigrationResponse,
  CacheClearResponse,
} from "@/lib/api";

const navigationItems = [
  {
    id: "rank",
    icon: "🔍",
    label: "순위 검색",
    description: "네이버쇼핑에서 피싱템 상품의 노출 순위를 확인합니다.",
  },
  {
    id: "monitoring",
    icon: "📋",
    label: "모니터링 관리",
    description: "등록된 키워드와 상품의 순위 변화를 관리합니다.",
  },
  {
    id: "keywords",
    icon: "📊",
    label: "키워드 분석",
    description: "검색량·연관 키워드·대표 카테고리를 분석합니다.",
  },
  {
    id: "advertising",
    icon: "📢",
    label: "광고 진단 & 시즌",
    description: "검색광고 상태와 시즌별 판매 기회를 진단합니다.",
  },
  {
    id: "cross-purchase",
    icon: "🛒",
    label: "교차구매 분석",
    description: "주문 데이터를 바탕으로 함께 구매한 상품을 분석합니다.",
  },
  {
    id: "candidates",
    icon: "🎯",
    label: "사입 후보 발굴",
    description: "분석 자료에서 판매 가능성이 높은 후보 상품을 찾습니다.",
  },
  {
    id: "data",
    icon: "⚙️",
    label: "데이터 관리",
    description: "저장 데이터와 이전 작업을 관리합니다.",
  },
] as const;

type NavigationId = (typeof navigationItems)[number]["id"];

export default function Home() {
  const [authenticated, setAuthenticated] = useState(false);
  const [checkingAuthentication, setCheckingAuthentication] =
    useState(true);
  const [loginPending, setLoginPending] = useState(false);
  const [activeNavigation, setActiveNavigation] =
    useState<NavigationId>("rank");
  const [visitedNavigations, setVisitedNavigations] =
    useState<NavigationId[]>(["rank"]);
  const [loginMessage, setLoginMessage] = useState("");

  const sheetUrl =
    process.env.NEXT_PUBLIC_GOOGLE_SHEET_URL ?? "";

  const activeItem =
    navigationItems.find((item) => item.id === activeNavigation) ??
    navigationItems[0];

  useEffect(() => {
    let active = true;

    getAuthenticationStatus()
      .then((result) => {
        if (active) {
          setAuthenticated(result.authenticated);
        }
      })
      .catch(() => {
        if (active) {
          setAuthenticated(false);
        }
      })
      .finally(() => {
        if (active) {
          setCheckingAuthentication(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  async function handleLogin(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();
    const loginForm = event.currentTarget;
    setLoginPending(true);
    setLoginMessage("");

    const formData = new FormData(event.currentTarget);
    const password = String(
      formData.get("password") ?? "",
    );

    try {
      const result = await loginWithPassword(password);
      setAuthenticated(result.authenticated);
      loginForm.reset();
    } catch (error) {
      setAuthenticated(false);
      setLoginMessage(
        error instanceof ApiError
          ? error.message
          : "백엔드 서버에 연결하지 못했습니다.",
      );
    } finally {
      setLoginPending(false);
    }
  }

  async function handleLogout() {
    try {
      await logoutSession();
    } finally {
      setAuthenticated(false);
      setLoginMessage("");
    }
  }

  if (checkingAuthentication) {
    return (
      <main className="login-page">
        <section className="login-card">
          <div className="login-logo-wrap">
            <Image
              src="/logo.png"
              alt="피싱템 로고"
              width={110}
              height={110}
              className="login-logo"
              priority
            />
          </div>
          <p className="eyebrow">FISHINGTEM RANK RADAR</p>
          <h1>접속 상태 확인 중</h1>
          <p className="login-description">
            안전한 로그인 상태를 확인하고 있습니다.
          </p>
        </section>
      </main>
    );
  }

  if (!authenticated) {
    return (
      <main className="login-page">
        <section className="login-card">
          <div className="login-logo-wrap">
            <Image
              src="/logo.png"
              alt="피싱템 로고"
              width={110}
              height={110}
              className="login-logo"
              priority
            />
          </div>

          <p className="eyebrow">FISHINGTEM RANK RADAR</p>
          <h1>🔐 피싱템 보안 접속</h1>
          <p className="login-description">
            허가된 사용자만 이용할 수 있습니다.
          </p>

          <form className="login-form" onSubmit={handleLogin}>
            <label htmlFor="password">접속 비밀번호</label>
            <input
              id="password"
              name="password"
              type="password"
              placeholder="비밀번호를 입력하세요"
              autoComplete="current-password"
              disabled={loginPending}
              required
            />

            <button
              className="primary-button"
              type="submit"
              disabled={loginPending}
            >
              {loginPending ? "로그인 확인 중..." : "로그인"}
            </button>
          </form>

          {loginMessage && (
            <div className="info-message">{loginMessage}</div>
          )}

        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="brand-area">
          <Image
            src="/logo.png"
            alt="피싱템 로고"
            width={72}
            height={72}
            className="header-logo"
            priority
          />

          <div>
            <p className="eyebrow">FISHINGTEM RANK RADAR</p>
            <h1>🎣 피싱템 순위 레이더</h1>
            <p className="header-description">
              쇼핑 순위·키워드·광고·상품 분석 통합 시스템
            </p>
          </div>
        </div>

        <div className="header-actions">
          {sheetUrl ? (
            <a
              href={sheetUrl}
              target="_blank"
              rel="noreferrer"
              className="secondary-button"
            >
              📗 Google Sheets
            </a>
          ) : (
            <button type="button" className="secondary-button" disabled>
              📗 Google Sheets
            </button>
          )}

          <button
            type="button"
            className="logout-button"
            onClick={handleLogout}
          >
            로그아웃
          </button>
        </div>
      </header>

      <section className="status-row">
        <span className="status-badge">
          <span className="status-dot" />
          Netlify 웹 전환 작업 중
        </span>
        <span>기존 Streamlit 프로그램은 정상 운영 중입니다.</span>
      </section>

      <nav className="main-navigation" aria-label="주요 메뉴">
        {navigationItems.map((item) => (
          <button
            key={item.id}
            type="button"
            className={
              activeNavigation === item.id
                ? "navigation-button active"
                : "navigation-button"
            }
            onClick={() => {
              setActiveNavigation(item.id);
              setVisitedNavigations((current) =>
                current.includes(item.id)
                  ? current
                  : [...current, item.id],
              );
            }}
          >
            <span>{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>

      <section className="content-card">
        <div className="content-heading">
          <div className="section-icon">{activeItem.icon}</div>
          <div>
            <p className="eyebrow">FISHINGTEM ANALYSIS</p>
            <h2>{activeItem.label}</h2>
            <p>{activeItem.description}</p>
          </div>
        </div>

        {visitedNavigations.includes("rank") && (
          <div
            style={{
              display:
                activeNavigation === "rank"
                  ? "block"
                  : "none",
            }}
          >
            <RankSearchPreview />
          </div>
        )}

        {visitedNavigations.includes("monitoring") && (
          <div
            style={{
              display:
                activeNavigation === "monitoring"
                  ? "block"
                  : "none",
            }}
          >
            <MonitoringManager />
          </div>
        )}

        {visitedNavigations.includes("keywords") && (
          <div
            style={{
              display:
                activeNavigation === "keywords"
                  ? "block"
                  : "none",
            }}
          >
            <KeywordAnalysis />
          </div>
        )}

        {visitedNavigations.includes("advertising") && (
          <div
            style={{
              display:
                activeNavigation === "advertising"
                  ? "block"
                  : "none",
            }}
          >
            <AdvertisingDiagnosis />
          </div>
        )}

        {visitedNavigations.includes("cross-purchase") && (
          <div
            style={{
              display:
                activeNavigation === "cross-purchase"
                  ? "block"
                  : "none",
            }}
          >
            <CrossPurchaseAnalysis />
          </div>
        )}

        {visitedNavigations.includes("candidates") && (
          <div
            style={{
              display:
                activeNavigation === "candidates"
                  ? "block"
                  : "none",
            }}
          >
            <CandidateAnalysis />
          </div>
        )}

        {visitedNavigations.includes("data") && (
          <div
            style={{
              display:
                activeNavigation === "data"
                  ? "block"
                  : "none",
            }}
          >
            <DataManagement />
          </div>
        )}
      </section>

      <footer className="app-footer">
        피싱템 내부 업무 시스템 · Netlify V2 전환 화면
      </footer>
    </main>
  );
}

function RankSearchPreview() {
  const [keyword, setKeyword] = useState("");
  const [limit, setLimit] = useState(400);
  const [
    includeSpecialProducts,
    setIncludeSpecialProducts,
  ] = useState(false);
  const [searchPending, setSearchPending] =
    useState(false);
  const [searchError, setSearchError] = useState("");
  const [searchResult, setSearchResult] =
    useState<RankSearchResponse | null>(null);
  const [selectedKeys, setSelectedKeys] =
    useState<string[]>([]);
  const [savePending, setSavePending] =
    useState(false);
  const [saveError, setSaveError] = useState("");
  const [saveResult, setSaveResult] =
    useState<SaveSelectedRankResponse | null>(null);

  function itemKey(item: RankSearchItem) {
    return (
      item.product_id ||
      `${item.rank}|${item.title}`
    );
  }

  async function handleRankSearch(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    const trimmedKeyword = keyword.trim();

    if (!trimmedKeyword) {
      setSearchError("검색 키워드를 입력해 주세요.");
      return;
    }

    setSearchPending(true);
    setSearchError("");
    setSaveError("");
    setSaveResult(null);
    setSelectedKeys([]);

    try {
      const result = await searchRank(
        trimmedKeyword,
        limit,
        includeSpecialProducts,
      );
      setSearchResult(result);
    } catch (error) {
      setSearchResult(null);
      setSearchError(
        error instanceof ApiError
          ? error.message
          : "순위 검색 서버에 연결하지 못했습니다.",
      );
    } finally {
      setSearchPending(false);
    }
  }

  function toggleItem(item: RankSearchItem) {
    const key = itemKey(item);

    setSelectedKeys((current) =>
      current.includes(key)
        ? current.filter((value) => value !== key)
        : [...current, key],
    );
  }

  function toggleAllItems() {
    if (!searchResult) {
      return;
    }

    const allKeys = searchResult.results.map(itemKey);

    setSelectedKeys((current) =>
      current.length === allKeys.length
        ? []
        : allKeys,
    );
  }

  async function handleSaveSelected() {
    if (!searchResult) {
      return;
    }

    const selectedItems =
      searchResult.results.filter((item) =>
        selectedKeys.includes(itemKey(item)),
      );

    if (selectedItems.length === 0) {
      setSaveError("저장할 상품을 선택해 주세요.");
      return;
    }

    setSavePending(true);
    setSaveError("");
    setSaveResult(null);

    try {
      const result = await saveSelectedRankItems(
        searchResult.keyword,
        selectedItems,
      );

      setSaveResult(result);
      setSelectedKeys([]);
    } catch (error) {
      setSaveError(
        error instanceof ApiError
          ? error.message
          : "선택 상품을 저장하지 못했습니다.",
      );
    } finally {
      setSavePending(false);
    }
  }

  const priceSummary =
    searchResult?.top10_price_summary;

  return (
    <>
      <form
        className="search-panel rank-search-panel"
        onSubmit={handleRankSearch}
      >
        <div className="field-group">
          <label htmlFor="rank-keyword">
            검색 키워드
          </label>
          <input
            id="rank-keyword"
            type="text"
            placeholder="예: 타이라바 로드"
            value={keyword}
            onChange={(event) =>
              setKeyword(event.target.value)
            }
            disabled={searchPending}
          />
        </div>

        <div className="field-group">
          <label htmlFor="rank-limit">
            조회 범위
          </label>
          <select
            id="rank-limit"
            value={limit}
            onChange={(event) =>
              setLimit(Number(event.target.value))
            }
            disabled={searchPending}
          >
            <option value="100">100위까지</option>
            <option value="200">200위까지</option>
            <option value="300">300위까지</option>
            <option value="400">400위까지</option>
          </select>
        </div>

        <label className="rank-special-option">
          <input
            type="checkbox"
            checked={includeSpecialProducts}
            disabled={searchPending}
            onChange={(event) =>
              setIncludeSpecialProducts(
                event.target.checked,
              )
            }
          />
          <span>
            중고·렌탈·해외직구 포함
          </span>
        </label>

        <button
          className="primary-button search-button"
          type="submit"
          disabled={searchPending}
        >
          {searchPending
            ? "정밀 검색 중..."
            : `🚀 ${limit}위까지 정밀 수색`}
        </button>
      </form>

      {searchError && (
        <div className="error-message">
          {searchError}
        </div>
      )}

      {searchResult?.warnings.map((warning) => (
        <div
          className="info-message"
          key={warning}
        >
          ⚠️ {warning}
        </div>
      ))}

      <div className="metric-grid">
        <article className="metric-card">
          <span>검색 키워드</span>
          <strong>
            {searchResult?.keyword ?? "-"}
          </strong>
        </article>

        <article className="metric-card">
          <span>피싱템 노출 상품</span>
          <strong>
            {searchResult?.match_count ?? 0}개
          </strong>
        </article>

        <article className="metric-card">
          <span>최고 순위</span>
          <strong>
            {searchResult?.best_rank
              ? `${searchResult.best_rank}위`
              : "-"}
          </strong>
        </article>

        <article className="metric-card">
          <span>조회 범위·처리시간</span>
          <strong>
            {searchResult
              ? `${searchResult.limit}위 · ${searchResult.elapsed_seconds}초`
              : `${limit}위`}
          </strong>
        </article>
      </div>

      {!searchResult ? (
        <div className="empty-state">
          <span>🔎</span>
          <h3>검색 결과가 여기에 표시됩니다.</h3>
          <p>
            검색만으로는 Google Sheets에 저장되지
            않습니다.
          </p>
        </div>
      ) : (
        <div className="rank-results">
          <div className="latest-collection-info">
            검색 키워드:{" "}
            <strong>{searchResult.keyword}</strong>
            {" · "}검색 시각:{" "}
            <strong>{searchResult.searched_at}</strong>
            {" · "}
            {searchResult.include_special_products
              ? "중고·렌탈·해외직구 포함"
              : "중고·렌탈·해외직구 제외"}
          </div>

          {priceSummary &&
            priceSummary.count > 0 && (
              <>
                <h3 className="rank-section-title">
                  💰 키워드 시장 가격 분석
                </h3>

                <div className="metric-grid">
                  <article className="metric-card">
                    <span>TOP10 최저가</span>
                    <strong>
                      {priceSummary.lowest
                        .toLocaleString()}원
                    </strong>
                  </article>

                  <article className="metric-card">
                    <span>TOP10 평균가</span>
                    <strong>
                      {priceSummary.average
                        .toLocaleString()}원
                    </strong>
                  </article>

                  <article className="metric-card">
                    <span>TOP10 최고가</span>
                    <strong>
                      {priceSummary.highest
                        .toLocaleString()}원
                    </strong>
                  </article>

                  <article className="metric-card">
                    <span>피싱템 평균가</span>
                    <strong>
                      {priceSummary.our_average
                        ? `${priceSummary.our_average
                            .toLocaleString()}원`
                        : "-"}
                    </strong>
                  </article>
                </div>

                {priceSummary.difference_percent !==
                  null && (
                  <div className="info-message">
                    피싱템 평균가격이 TOP10 평균보다{" "}
                    {Math.abs(
                      priceSummary.difference_percent,
                    )}
                    %{" "}
                    {priceSummary.difference_percent > 0
                      ? "높습니다."
                      : "낮습니다."}
                  </div>
                )}
              </>
            )}

          {searchResult.market_top10.length > 0 && (
            <>
              <h3 className="rank-section-title">
                🏪 시장 경쟁 상품 TOP 10
              </h3>

              <div className="table-scroll">
                <table className="result-table rank-market-table">
                  <thead>
                    <tr>
                      <th>순위</th>
                      <th>이미지</th>
                      <th>상품명</th>
                      <th>판매처</th>
                      <th>가격</th>
                      <th>유형</th>
                      <th>링크</th>
                    </tr>
                  </thead>
                  <tbody>
                    {searchResult.market_top10.map(
                      (item) => (
                        <tr
                          key={`market-${itemKey(item)}`}
                        >
                          <td>
                            <strong>{item.rank}위</strong>
                          </td>
                          <td>
                            {item.image ? (
                              <img
                                src={item.image}
                                alt=""
                                className="rank-thumbnail"
                              />
                            ) : (
                              "-"
                            )}
                          </td>
                          <td>{item.title}</td>
                          <td>{item.mall_name}</td>
                          <td>
                            {item.price
                              .toLocaleString()}원
                          </td>
                          <td>
                            <span className="catalog-badge">
                              {item.catalog_badge}
                            </span>
                          </td>
                          <td>
                            {item.link ? (
                              <a
                                href={item.link}
                                target="_blank"
                                rel="noreferrer"
                                className="product-link"
                              >
                                상품 보기
                              </a>
                            ) : (
                              "-"
                            )}
                          </td>
                        </tr>
                      ),
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <h3 className="rank-section-title">
            📌 저장 및 모니터링할 상품 선택
          </h3>

          <p className="rank-save-notice">
            검색만으로는 저장되지 않습니다. 선택한
            상품만 통합 순위기록에 저장되고 모니터링에
            등록됩니다.
          </p>

          {searchResult.results.length === 0 ? (
            <div className="empty-state compact-state">
              <span>📭</span>
              <h3>
                {searchResult.limit}위 내에 피싱템 상품이
                없습니다.
              </h3>
              <p>
                네이버쇼핑 상품{" "}
                {searchResult.fetched_count
                  .toLocaleString()}개를 확인했습니다.
              </p>
            </div>
          ) : (
            <>
              <div className="rank-selection-toolbar">
                <label>
                  <input
                    type="checkbox"
                    checked={
                      selectedKeys.length > 0 &&
                      selectedKeys.length ===
                        searchResult.results.length
                    }
                    onChange={toggleAllItems}
                    disabled={savePending}
                  />
                  전체 선택
                </label>

                <strong>
                  선택 {selectedKeys.length}개
                </strong>
              </div>

              <div className="table-scroll">
                <table className="result-table">
                  <thead>
                    <tr>
                      <th>선택</th>
                      <th>순위</th>
                      <th>이미지</th>
                      <th>상품명</th>
                      <th>판매처</th>
                      <th>가격</th>
                      <th>노출 유형</th>
                      <th>카테고리</th>
                      <th>링크</th>
                    </tr>
                  </thead>

                  <tbody>
                    {searchResult.results.map(
                      (item) => {
                        const key = itemKey(item);

                        return (
                          <tr key={`ours-${key}`}>
                            <td>
                              <input
                                type="checkbox"
                                aria-label={
                                  `${item.title} 선택`
                                }
                                checked={selectedKeys
                                  .includes(key)}
                                disabled={savePending}
                                onChange={() =>
                                  toggleItem(item)
                                }
                              />
                            </td>
                            <td>
                              <strong>
                                {item.rank}위
                              </strong>
                            </td>
                            <td>
                              {item.image ? (
                                <img
                                  src={item.image}
                                  alt=""
                                  className="rank-thumbnail"
                                />
                              ) : (
                                "-"
                              )}
                            </td>
                            <td>{item.title}</td>
                            <td>{item.mall_name}</td>
                            <td>
                              {item.price
                                .toLocaleString()}원
                            </td>
                            <td>
                              <span className="catalog-badge">
                                {item.is_catalog
                                  ? "🔗 "
                                  : "✅ "}
                                {item.catalog_badge}
                              </span>
                            </td>
                            <td>
                              {item.categories
                                .filter(Boolean)
                                .join(" > ") || "-"}
                            </td>
                            <td>
                              {item.link ? (
                                <a
                                  href={item.link}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="product-link"
                                >
                                  상품 보기
                                </a>
                              ) : (
                                "-"
                              )}
                            </td>
                          </tr>
                        );
                      },
                    )}
                  </tbody>
                </table>
              </div>

              <button
                type="button"
                className="primary-button rank-save-button"
                disabled={
                  savePending ||
                  selectedKeys.length === 0
                }
                onClick={() =>
                  void handleSaveSelected()
                }
              >
                {savePending
                  ? "선택 상품 저장 중..."
                  : `🚀 선택 ${selectedKeys.length}개 저장 및 모니터링 등록`}
              </button>
            </>
          )}

          {saveResult && (
            <>
              <div className="success-message">
                {saveResult.message}
              </div>

              {saveResult.monitor_duplicate_count > 0 && (
                <div className="info-message">
                  이미 등록된 모니터링 상품{" "}
                  {saveResult.monitor_duplicate_count}건은
                  중복 등록하지 않았습니다.
                </div>
              )}

              {saveResult.monitor_errors.map(
                (message) => (
                  <div
                    className="error-message"
                    key={message}
                  >
                    모니터링 등록 오류: {message}
                  </div>
                ),
              )}
            </>
          )}

          {saveError && (
            <div className="error-message">
              {saveError}
            </div>
          )}
        </div>
      )}
    </>
  );
}

function MonitoringManager() {
  const [items, setItems] = useState<MonitorItem[]>([]);
  const [historyById, setHistoryById] = useState<
    Record<string, MonitoringHistoryItem>
  >({});
  const [selectedIds, setSelectedIds] =
    useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionPending, setActionPending] =
    useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [collecting, setCollecting] = useState(false);
  const [collectResult, setCollectResult] =
    useState<MonitoringCollectResponse | null>(null);

  async function loadItems() {
    setLoading(true);
    setError("");

    try {
      const [listResult, historyResult] =
        await Promise.all([
          getMonitoringList(),
          getMonitoringHistory(),
        ]);

      setItems(listResult.items);
      setHistoryById(
        Object.fromEntries(
          historyResult.items.map((item) => [
            item.item_id,
            item,
          ]),
        ),
      );
      setSelectedIds([]);
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "모니터링 목록을 불러오지 못했습니다.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadItems();
  }, []);

  async function handleAdd(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);

    setActionPending(true);
    setMessage("");
    setError("");

    try {
      const result = await addMonitoringItem({
        keyword: String(
          formData.get("keyword") ?? "",
        ).trim(),
        memo: String(
          formData.get("memo") ?? "",
        ).trim(),
        product_id: String(
          formData.get("product_id") ?? "",
        ).trim(),
        product_name: String(
          formData.get("product_name") ?? "",
        ).trim(),
      });

      setMessage(result.message);
      form.reset();
      await loadItems();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "모니터링 항목을 등록하지 못했습니다.",
      );
    } finally {
      setActionPending(false);
    }
  }

  async function handleDelete() {
    if (selectedIds.length === 0) {
      setError("삭제할 항목을 선택해 주세요.");
      return;
    }

    if (
      !window.confirm(
        `선택한 ${selectedIds.length}개 항목을 삭제할까요?`,
      )
    ) {
      return;
    }

    setActionPending(true);
    setMessage("");
    setError("");

    try {
      const result = await deleteMonitoringItems(
        selectedIds,
      );
      setMessage(result.message);
      await loadItems();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "모니터링 항목을 삭제하지 못했습니다.",
      );
    } finally {
      setActionPending(false);
    }
  }

  async function handleCollect() {
    setCollecting(true);
    setMessage("");
    setError("");
    setCollectResult(null);

    try {
      const result = await collectMonitoringRanks();
      setCollectResult(result);
      setMessage(
        `전체 ${result.total_items}개 항목의 순위 수집을 완료했습니다.`,
      );
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "모니터링 순위를 수집하지 못했습니다.",
      );
    } finally {
      setCollecting(false);
    }
  }

  function toggleSelection(itemId: string) {
    setSelectedIds((current) =>
      current.includes(itemId)
        ? current.filter((id) => id !== itemId)
        : [...current, itemId],
    );
  }

  function toggleAll() {
    setSelectedIds((current) =>
      current.length === items.length
        ? []
        : items.map((item) => item.item_id),
    );
  }

  return (
    <>
      <form
        className="monitor-form"
        onSubmit={handleAdd}
      >
        <div className="field-group">
          <label htmlFor="monitor-keyword">
            키워드
          </label>
          <input
            id="monitor-keyword"
            name="keyword"
            placeholder="예: 낚시의자"
            disabled={actionPending}
            required
          />
        </div>

        <div className="field-group">
          <label htmlFor="monitor-product-id">
            productId · 선택
          </label>
          <input
            id="monitor-product-id"
            name="product_id"
            placeholder="특정 상품만 추적할 때 입력"
            disabled={actionPending}
          />
        </div>

        <div className="field-group">
          <label htmlFor="monitor-product-name">
            상품명 · 선택
          </label>
          <input
            id="monitor-product-name"
            name="product_name"
            placeholder="관리용 상품명"
            disabled={actionPending}
          />
        </div>

        <div className="field-group">
          <label htmlFor="monitor-memo">
            메모 · 선택
          </label>
          <input
            id="monitor-memo"
            name="memo"
            placeholder="관리 메모"
            disabled={actionPending}
          />
        </div>

        <button
          type="submit"
          className="primary-button monitor-add-button"
          disabled={actionPending}
        >
          {actionPending
            ? "처리 중..."
            : "＋ 모니터링 등록"}
        </button>
      </form>

      {message && (
        <div className="success-message">
          {message}
        </div>
      )}

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      <div className="monitor-toolbar">
        <strong>
          등록 항목 {items.length}개
        </strong>

        <div>
          <button
            type="button"
            className="primary-button"
            onClick={() => void handleCollect()}
            disabled={
              loading ||
              actionPending ||
              collecting ||
              items.length === 0
            }
          >
            {collecting
              ? "전체 순위 수집 중..."
              : "🔄 전체 순위 수집"}
          </button>

          <button
            type="button"
            className="secondary-button"
            onClick={() => void loadItems()}
            disabled={
              loading ||
              actionPending ||
              collecting
            }
          >
            새로고침
          </button>

          <button
            type="button"
            className="logout-button"
            onClick={() => void handleDelete()}
            disabled={
              actionPending ||
              selectedIds.length === 0
            }
          >
            선택 삭제 ({selectedIds.length})
          </button>
        </div>
      </div>

      {collectResult && (
        <section className="collection-result">
          <div className="metric-grid">
            <article className="metric-card">
              <span>전체 항목</span>
              <strong>
                {collectResult.total_items}
              </strong>
            </article>

            <article className="metric-card">
              <span>노출·미노출</span>
              <strong>
                {collectResult.exposed_count} ·{" "}
                {collectResult.not_exposed_count}
              </strong>
            </article>

            <article className="metric-card">
              <span>시트 저장</span>
              <strong>
                {collectResult.saved_records}건
              </strong>
            </article>

            <article className="metric-card">
              <span>처리시간·오류</span>
              <strong>
                {collectResult.elapsed_seconds}초 ·{" "}
                {collectResult.error_count}건
              </strong>
            </article>
          </div>

          <div className="table-scroll">
            <table className="result-table collection-table">
              <thead>
                <tr>
                  <th>키워드</th>
                  <th>추적 상품</th>
                  <th>최신 순위</th>
                  <th>상태</th>
                  <th>검색 결과</th>
                </tr>
              </thead>

              <tbody>
                {collectResult.results.map((result) => (
                  <tr key={result.item_id}>
                    <td>
                      <strong>{result.keyword}</strong>
                    </td>
                    <td>
                      {result.product_name ||
                        "전체 피싱템 상품"}
                    </td>
                    <td>
                      {result.rank
                        ? `${result.rank}위`
                        : "-"}
                    </td>
                    <td>
                      <span
                        className={`collection-status ${result.status}`}
                      >
                        {result.status === "exposed"
                          ? "노출"
                          : result.status === "not_exposed"
                            ? "미노출"
                            : "오류"}
                      </span>
                    </td>
                    <td>{result.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {loading ? (
        <div className="empty-state compact-state">
          <span>⏳</span>
          <h3>모니터링 목록을 불러오는 중입니다.</h3>
        </div>
      ) : items.length === 0 ? (
        <div className="empty-state compact-state">
          <span>📋</span>
          <h3>등록된 모니터링 항목이 없습니다.</h3>
        </div>
      ) : (
        <div className="table-scroll">
          <table className="result-table">
            <thead>
              <tr>
                <th>
                  <input
                    type="checkbox"
                    aria-label="전체 선택"
                    checked={
                      items.length > 0 &&
                      selectedIds.length === items.length
                    }
                    onChange={toggleAll}
                  />
                </th>
                <th>키워드</th>
                <th>상품명</th>
                <th>최신 순위</th>
                <th>순위 변화</th>
                <th>마지막 수집</th>
                <th>productId</th>
                <th>메모</th>
                <th>등록일</th>
              </tr>
            </thead>

            <tbody>
              {items.map((item) => {
                const history =
                  historyById[item.item_id];

                return (
                  <tr key={item.item_id}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`${item.keyword} 선택`}
                        checked={selectedIds.includes(
                          item.item_id,
                        )}
                        onChange={() =>
                          toggleSelection(item.item_id)
                        }
                      />
                    </td>
                    <td>
                      <strong>{item.keyword}</strong>
                    </td>
                    <td>{item.product_name || "-"}</td>
                    <td>
                      <strong className="latest-rank">
                        {history?.latest_rank
                          ? `${history.latest_rank}위`
                          : "-"}
                      </strong>
                    </td>
                    <td>
                      <RankChangeBadge
                        history={history}
                      />
                    </td>
                    <td>
                      {history?.latest_collected_at ||
                        "-"}
                    </td>
                    <td>{item.product_id || "-"}</td>
                    <td>{item.memo || "-"}</td>
                    <td>{item.registered_at || "-"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function KeywordAnalysis() {
  const [keyword, setKeyword] = useState("");
  const [relatedLimit, setRelatedLimit] =
    useState<10 | 20 | 30>(20);
  const [activeTab, setActiveTab] = useState<
    "keywords" | "categories"
  >("keywords");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] =
    useState<KeywordAnalysisResponse | null>(null);

  async function handleAnalyze(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    const trimmedKeyword = keyword.trim();

    if (!trimmedKeyword) {
      setError("분석할 키워드를 입력해 주세요.");
      return;
    }

    setPending(true);
    setError("");

    try {
      const response = await analyzeKeywords(
        trimmedKeyword,
        relatedLimit,
      );
      setResult(response);
    } catch (requestError) {
      setResult(null);
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "키워드 분석 서버에 연결하지 못했습니다.",
      );
    } finally {
      setPending(false);
    }
  }

  function displayVolume(
    raw: string,
    value: number,
  ) {
    if (
      raw.replace(/\s/g, "") === "<10" ||
      raw === "10미만"
    ) {
      return "< 10";
    }

    return value.toLocaleString();
  }

  return (
    <>
      <form
        className="keyword-analysis-form"
        onSubmit={handleAnalyze}
      >
        <div className="field-group">
          <label htmlFor="analysis-keyword">
            분석 키워드
          </label>
          <input
            id="analysis-keyword"
            value={keyword}
            onChange={(event) =>
              setKeyword(event.target.value)
            }
            placeholder="예: 낚시의자"
            disabled={pending}
          />
        </div>

        <div className="category-preview">
          <span>대표 카테고리</span>
          <strong>
            {result?.summary
              .representative_category ||
              "분석 후 표시됩니다."}
          </strong>
        </div>

        <div className="field-group">
          <label htmlFor="related-limit">
            연관 키워드
          </label>
          <select
            id="related-limit"
            value={relatedLimit}
            onChange={(event) =>
              setRelatedLimit(
                Number(event.target.value) as
                  | 10
                  | 20
                  | 30,
              )
            }
            disabled={pending}
          >
            <option value="10">10개</option>
            <option value="20">20개</option>
            <option value="30">30개</option>
          </select>
        </div>

        <button
          type="submit"
          className="primary-button"
          disabled={pending}
        >
          {pending
            ? "키워드 분석 중..."
            : "📊 키워드 분석"}
        </button>
      </form>

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      {result && (
        <>
          <div className="metric-grid keyword-metrics">
            <article className="metric-card">
              <span>PC 검색량</span>
              <strong>
                {displayVolume(
                  result.summary.pc_volume_raw,
                  result.summary.pc_volume,
                )}
              </strong>
            </article>

            <article className="metric-card">
              <span>모바일 검색량</span>
              <strong>
                {displayVolume(
                  result.summary.mobile_volume_raw,
                  result.summary.mobile_volume,
                )}
              </strong>
            </article>

            <article className="metric-card">
              <span>총 검색량</span>
              <strong>
                {result.summary.total_volume
                  .toLocaleString()}
              </strong>
            </article>

            <article className="metric-card">
              <span>쇼핑 상품 수·처리시간</span>
              <strong>
                {result.summary.product_count
                  .toLocaleString()}{" "}
                · {result.elapsed_seconds}초
              </strong>
            </article>
          </div>

          <div className="analysis-tabs">
            <button
              type="button"
              className={
                activeTab === "keywords"
                  ? "analysis-tab active"
                  : "analysis-tab"
              }
              onClick={() =>
                setActiveTab("keywords")
              }
            >
              키워드 분석
            </button>

            <button
              type="button"
              className={
                activeTab === "categories"
                  ? "analysis-tab active"
                  : "analysis-tab"
              }
              onClick={() =>
                setActiveTab("categories")
              }
            >
              Category Analysis
            </button>
          </div>

          {activeTab === "keywords" ? (
            <div className="table-scroll">
              <table className="result-table">
                <thead>
                  <tr>
                    <th>키워드</th>
                    <th>PC 검색량</th>
                    <th>모바일 검색량</th>
                    <th>총 검색량</th>
                    <th>쇼핑 상품 수</th>
                    <th>경쟁도</th>
                  </tr>
                </thead>

                <tbody>
                  {result.keywords.map((item) => (
                    <tr key={item.keyword}>
                      <td>
                        <strong>
                          {item.keyword}
                        </strong>
                      </td>
                      <td>
                        {displayVolume(
                          item.pc_volume_raw,
                          item.pc_volume,
                        )}
                      </td>
                      <td>
                        {displayVolume(
                          item.mobile_volume_raw,
                          item.mobile_volume,
                        )}
                      </td>
                      <td>
                        {item.total_volume
                          .toLocaleString()}
                      </td>
                      <td>
                        {item.product_count
                          .toLocaleString()}
                      </td>
                      <td>
                        {item.competition || "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="table-scroll">
              <table className="result-table category-table">
                <thead>
                  <tr>
                    <th>키워드</th>
                    <th>대표 카테고리</th>
                  </tr>
                </thead>

                <tbody>
                  {result.keywords.map((item) => (
                    <tr key={item.keyword}>
                      <td>
                        <strong>
                          {item.keyword}
                        </strong>
                      </td>
                      <td>
                        {item.representative_category ||
                          "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {!result && !pending && (
        <div className="empty-state">
          <span>📊</span>
          <h3>
            검색량과 대표 카테고리를 분석합니다.
          </h3>
          <p>
            키워드를 입력하고 분석 버튼을 눌러주세요.
          </p>
        </div>
      )}
    </>
  );
}



function CandidateAnalysis() {
  const [masterFile, setMasterFile] =
    useState<File | null>(null);
  const [keywords, setKeywords] = useState("");
  const [maxResults, setMaxResults] =
    useState<100 | 200 | 300 | 400>(100);
  const [resultLimit, setResultLimit] =
    useState(100);
  const [minVolume, setMinVolume] = useState(10);
  const [excludeOwned, setExcludeOwned] =
    useState(true);
  const [excludeGroup, setExcludeGroup] =
    useState(false);
  const [excludeUsed, setExcludeUsed] =
    useState(true);
  const [excludeRental, setExcludeRental] =
    useState(true);
  const [excludeOverseas, setExcludeOverseas] =
    useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] =
    useState<CandidateAnalysisResponse | null>(null);

  async function handleAnalyze(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    if (!masterFile) {
      setError("자사 상품 마스터 Excel 또는 CSV 파일을 선택해 주세요.");
      return;
    }

    if (!keywords.trim()) {
      setError("기준 검색어를 한 개 이상 입력해 주세요.");
      return;
    }

    setPending(true);
    setError("");

    try {
      const response = await analyzeCandidates(
        masterFile,
        keywords,
        {
          maxResults,
          resultLimit,
          minVolume,
          excludeOwned,
          excludeGroup,
          excludeUsed,
          excludeRental,
          excludeOverseas,
        },
      );
      setResult(response);
    } catch (requestError) {
      setResult(null);
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "사입 후보 분석 서버에 연결하지 못했습니다.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="candidate-analysis">
      <div className="privacy-notice">
        <span>🔒 상품 마스터 보호</span>
        <p>
          업로드한 상품 마스터는 후보 판정에만 사용되며
          서버와 Google Sheets에 저장하지 않습니다.
        </p>
      </div>

      <form
        className="candidate-form"
        onSubmit={handleAnalyze}
      >
        <div className="candidate-input-grid">
          <div className="field-group">
            <label htmlFor="candidate-keywords">
              기준 검색어
            </label>
            <textarea
              id="candidate-keywords"
              value={keywords}
              onChange={(event) =>
                setKeywords(event.target.value)
              }
              placeholder={
                "검색어를 한 줄에 하나씩 입력하세요.\n" +
                "예: 낚시의자\n타이라바\n메탈지그"
              }
              disabled={pending}
              required
            />
          </div>

          <div className="field-group">
            <label htmlFor="candidate-master">
              자사 상품 마스터 Excel
            </label>
            <input
              id="candidate-master"
              type="file"
              accept=".xlsx,.xls,.csv"
              disabled={pending}
              onChange={(event) =>
                setMasterFile(
                  event.target.files?.[0] ?? null,
                )
              }
            />
            <small className="field-help">
              상품명 필수 · 상품번호·브랜드 권장
            </small>
          </div>
        </div>

        <div className="candidate-option-grid">
          <div className="field-group">
            <label htmlFor="candidate-max-results">
              검색어별 수집 상품
            </label>
            <select
              id="candidate-max-results"
              value={maxResults}
              disabled={pending}
              onChange={(event) =>
                setMaxResults(
                  Number(event.target.value) as
                    | 100
                    | 200
                    | 300
                    | 400,
                )
              }
            >
              <option value="100">100개</option>
              <option value="200">200개</option>
              <option value="300">300개</option>
              <option value="400">400개</option>
            </select>
          </div>

          <div className="field-group">
            <label htmlFor="candidate-limit">
              최종 후보 표시 수
            </label>
            <select
              id="candidate-limit"
              value={resultLimit}
              disabled={pending}
              onChange={(event) =>
                setResultLimit(
                  Number(event.target.value),
                )
              }
            >
              <option value="10">10개</option>
              <option value="50">50개</option>
              <option value="100">100개</option>
              <option value="200">200개</option>
              <option value="500">500개</option>
            </select>
          </div>

          <div className="field-group">
            <label htmlFor="candidate-min-volume">
              최소 월간 검색량
            </label>
            <input
              id="candidate-min-volume"
              type="number"
              min="0"
              max="1000000"
              value={minVolume}
              disabled={pending}
              onChange={(event) =>
                setMinVolume(
                  Math.max(
                    0,
                    Number(event.target.value),
                  ),
                )
              }
            />
          </div>
        </div>

        <div className="candidate-check-grid">
          <label>
            <input
              type="checkbox"
              checked={excludeOwned}
              disabled={pending}
              onChange={(event) =>
                setExcludeOwned(event.target.checked)
              }
            />
            자사 동일상품 제외
          </label>

          <label>
            <input
              type="checkbox"
              checked={excludeGroup}
              disabled={pending}
              onChange={(event) =>
                setExcludeGroup(event.target.checked)
              }
            />
            동일제품군 제외
          </label>

          <label>
            <input
              type="checkbox"
              checked={excludeUsed}
              disabled={pending}
              onChange={(event) =>
                setExcludeUsed(event.target.checked)
              }
            />
            중고상품 제외
          </label>

          <label>
            <input
              type="checkbox"
              checked={excludeRental}
              disabled={pending}
              onChange={(event) =>
                setExcludeRental(event.target.checked)
              }
            />
            렌탈상품 제외
          </label>

          <label>
            <input
              type="checkbox"
              checked={excludeOverseas}
              disabled={pending}
              onChange={(event) =>
                setExcludeOverseas(event.target.checked)
              }
            />
            해외직구 제외
          </label>
        </div>

        <button
          type="submit"
          className="primary-button candidate-submit"
          disabled={pending}
        >
          {pending
            ? "네이버쇼핑 후보 분석 중..."
            : "🚀 사입 후보 분석 실행"}
        </button>
      </form>

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      {!result && !pending && (
        <div className="empty-state compact-state">
          <span>🎯</span>
          <h3>미취급 사입 후보를 찾습니다.</h3>
          <p>
            검색어와 상품 마스터를 입력해 주세요.
          </p>
        </div>
      )}

      {result && (
        <>
          <div className="metric-grid candidate-metrics">
            <article className="metric-card">
              <span>분석 검색어</span>
              <strong>
                {result.summary.keyword_count}개
              </strong>
            </article>

            <article className="metric-card">
              <span>자사 상품</span>
              <strong>
                {result.summary.master_product_count
                  .toLocaleString()}개
              </strong>
            </article>

            <article className="metric-card">
              <span>발견 후보</span>
              <strong>
                {result.summary.candidate_count
                  .toLocaleString()}개
              </strong>
            </article>

            <article className="metric-card">
              <span>처리시간·오류</span>
              <strong>
                {result.elapsed_seconds}초 ·{" "}
                {result.summary.error_count}건
              </strong>
            </article>
          </div>

          {result.errors.length > 0 && (
            <div className="error-message">
              {result.errors.map((item) => (
                <div key={item.keyword}>
                  {item.keyword}: {item.message}
                </div>
              ))}
            </div>
          )}

          {result.results.length === 0 ? (
            <div className="empty-state compact-state">
              <span>📭</span>
              <h3>조건에 맞는 후보가 없습니다.</h3>
              <p>
                최소 검색량을 낮추거나 제외 조건을
                해제해 보세요.
              </p>
            </div>
          ) : (
            <div className="table-scroll">
              <table className="result-table candidate-table">
                <thead>
                  <tr>
                    <th>점수</th>
                    <th>상품명</th>
                    <th>최고순위</th>
                    <th>월간 검색량</th>
                    <th>대표가격</th>
                    <th>판매처</th>
                    <th>자사 취급</th>
                    <th>카테고리</th>
                    <th>링크</th>
                  </tr>
                </thead>

                <tbody>
                  {result.results.map((item) => (
                    <tr
                      key={
                        item.product_id ||
                        item.product_name
                      }
                    >
                      <td>
                        <strong className="candidate-score">
                          {item.potential_score
                            .toLocaleString()}
                        </strong>
                      </td>
                      <td>
                        <strong>
                          {item.product_name}
                        </strong>
                        <div className="candidate-subtext">
                          {item.brand ||
                            item.maker ||
                            "브랜드 정보 없음"}
                        </div>
                      </td>
                      <td>{item.best_rank}위</td>
                      <td>
                        {item.search_volume
                          .toLocaleString()}
                        <div className="candidate-subtext">
                          기준: {item.volume_keyword}
                        </div>
                      </td>
                      <td>
                        {item.representative_price
                          .toLocaleString()}원
                      </td>
                      <td>
                        {item.representative_seller ||
                          "-"}
                      </td>
                      <td>
                        <div className="candidate-badges">
                          <span
                            className={
                              item.same_product_owned
                                ? "candidate-badge owned"
                                : "candidate-badge new"
                            }
                          >
                            {item.same_product_owned
                              ? "동일상품 있음"
                              : "🆕 동일상품 없음"}
                          </span>
                          <span
                            className={
                              item.product_group_owned
                                ? "candidate-badge owned"
                                : "candidate-badge new"
                            }
                          >
                            {item.product_group_owned
                              ? "취급 제품군"
                              : "🆕 미취급군"}
                          </span>
                        </div>
                      </td>
                      <td>{item.category || "-"}</td>
                      <td>
                        {item.link ? (
                          <a
                            href={item.link}
                            target="_blank"
                            rel="noreferrer"
                            className="product-link"
                          >
                            상품 보기
                          </a>
                        ) : (
                          "-"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="candidate-guide">
            잠재력 점수는 월간 검색량, 최고 노출순위,
            검색 결과에서 관측된 판매처 수를 기준으로
            계산합니다. 실제 사입 전 도매가격·마진·MOQ와
            배송비를 별도로 확인하세요.
          </div>
        </>
      )}
    </section>
  );
}

function CrossPurchaseAnalysis() {
  const [files, setFiles] = useState<File[]>([]);
  const [targetQuery, setTargetQuery] = useState("");
  const [topN, setTopN] = useState(50);
  const [minOrders, setMinOrders] = useState(2);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] =
    useState<CrossPurchaseResponse | null>(null);

  async function handleAnalyze(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    if (files.length === 0) {
      setError("주문내역 엑셀 파일을 선택해 주세요.");
      return;
    }

    const normalizedQuery = targetQuery.trim();

    if (!normalizedQuery) {
      setError("기준 상품명 또는 검색어를 입력해 주세요.");
      return;
    }

    setPending(true);
    setError("");

    try {
      const response = await analyzeCrossPurchase(
        files,
        normalizedQuery,
        topN,
        minOrders,
      );
      setResult(response);
    } catch (requestError) {
      setResult(null);
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "교차구매 분석 서버에 연결하지 못했습니다.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="cross-purchase-analysis">
      <div className="privacy-notice">
        <span>🔒 개인정보 보호</span>
        <p>
          주문번호는 상품 묶음을 계산할 때만 사용됩니다.
          업로드 파일과 주문 정보는 서버나 Google Sheets에
          저장하지 않습니다.
        </p>
      </div>

      <form
        className="cross-purchase-form"
        onSubmit={handleAnalyze}
      >
        <div className="field-group cross-file-field">
          <label htmlFor="cross-files">
            주문내역 Excel 파일
          </label>
          <input
            id="cross-files"
            type="file"
            accept=".xlsx,.xls"
            multiple
            disabled={pending}
            onChange={(event) =>
              setFiles(
                Array.from(event.target.files ?? []),
              )
            }
          />
          <small>
            xlsx·xls 파일, 최대 10개 · 현재{" "}
            {files.length}개 선택
          </small>
        </div>

        <div className="field-group">
          <label htmlFor="cross-target">
            기준 상품명 또는 상품번호
          </label>
          <input
            id="cross-target"
            value={targetQuery}
            onChange={(event) =>
              setTargetQuery(event.target.value)
            }
            placeholder="예: 타이라바, 메탈지그, 에기"
            disabled={pending}
            required
          />
        </div>

        <div className="field-group">
          <label htmlFor="cross-top-n">
            표시할 연관상품 수
          </label>
          <select
            id="cross-top-n"
            value={topN}
            disabled={pending}
            onChange={(event) =>
              setTopN(Number(event.target.value))
            }
          >
            <option value="10">10개</option>
            <option value="20">20개</option>
            <option value="50">50개</option>
            <option value="100">100개</option>
            <option value="200">200개</option>
          </select>
        </div>

        <div className="field-group">
          <label htmlFor="cross-min-orders">
            최소 동시구매 주문 수
          </label>
          <input
            id="cross-min-orders"
            type="number"
            min="1"
            max="100"
            value={minOrders}
            disabled={pending}
            onChange={(event) =>
              setMinOrders(
                Math.max(
                  1,
                  Number(event.target.value),
                ),
              )
            }
          />
        </div>

        <button
          type="submit"
          className="primary-button cross-submit"
          disabled={pending}
        >
          {pending
            ? "주문내역 분석 중..."
            : "🔎 교차구매 분석 실행"}
        </button>
      </form>

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      {!result && !pending && (
        <div className="empty-state compact-state">
          <span>🛒</span>
          <h3>
            함께 구매된 상품을 분석합니다.
          </h3>
          <p>
            주문번호·상품명이 포함된 엑셀 파일을
            선택해 주세요.
          </p>
        </div>
      )}

      {result && (
        <>
          <div className="metric-grid cross-metrics">
            <article className="metric-card">
              <span>기준 상품</span>
              <strong>
                {result.target_query}
              </strong>
            </article>

            <article className="metric-card">
              <span>기준 상품 주문</span>
              <strong>
                {result.summary.target_order_count
                  .toLocaleString()}건
              </strong>
            </article>

            <article className="metric-card">
              <span>연관상품</span>
              <strong>
                {result.summary.result_count
                  .toLocaleString()}개
              </strong>
            </article>

            <article className="metric-card">
              <span>처리 행·시간</span>
              <strong>
                {result.summary.order_row_count
                  .toLocaleString()}행 ·{" "}
                {result.elapsed_seconds}초
              </strong>
            </article>
          </div>

          {result.file_errors.length > 0 && (
            <div className="error-message">
              일부 파일을 읽지 못했습니다.
              {result.file_errors.map((item) => (
                <div key={item.file_name}>
                  {item.file_name}: {item.message}
                </div>
              ))}
            </div>
          )}

          {result.summary.target_order_count === 0 ? (
            <div className="empty-state compact-state">
              <span>📭</span>
              <h3>
                기준 상품이 포함된 주문이 없습니다.
              </h3>
              <p>
                상품명 또는 상품번호를 다시 확인해 주세요.
              </p>
            </div>
          ) : result.results.length === 0 ? (
            <div className="empty-state compact-state">
              <span>📭</span>
              <h3>
                조건에 맞는 연관상품이 없습니다.
              </h3>
              <p>
                최소 동시구매 주문 수를 낮춰보세요.
              </p>
            </div>
          ) : (
            <div className="table-scroll">
              <table className="result-table cross-table">
                <thead>
                  <tr>
                    <th>순번</th>
                    <th>상품번호</th>
                    <th>함께 산 상품</th>
                    <th>함께 구매 주문수</th>
                    <th>동시구매율</th>
                    <th>우리 제품</th>
                  </tr>
                </thead>

                <tbody>
                  {result.results.map((item, index) => (
                    <tr
                      key={
                        `${item.product_id}-` +
                        `${item.product_name}`
                      }
                    >
                      <td>{index + 1}</td>
                      <td>{item.product_id || "-"}</td>
                      <td>
                        <strong>
                          {item.product_name}
                        </strong>
                      </td>
                      <td>
                        {item.together_order_count
                          .toLocaleString()}건
                      </td>
                      <td>
                        <strong className="cross-rate">
                          {item.cross_purchase_rate}%
                        </strong>
                      </td>
                      <td>
                        {item.is_ours ? (
                          <span className="our-product-badge">
                            ✅ 우리 제품
                          </span>
                        ) : (
                          "-"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function AdvertisingDiagnosis() {
  const [result, setResult] =
    useState<AdvertisingOverviewResponse | null>(
      null,
    );
  const [activeTab, setActiveTab] = useState<
    "campaigns" | "adgroups" | "season"
  >("campaigns");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [campaignQuery, setCampaignQuery] =
    useState("");
  const [
    selectedCampaignIds,
    setSelectedCampaignIds,
  ] = useState<string[]>([]);
  const [
    selectedAdgroupIds,
    setSelectedAdgroupIds,
  ] = useState<string[]>([]);

  async function loadAdvertising() {
    setLoading(true);
    setError("");

    try {
      const response =
        await getAdvertisingOverview();

      setResult(response);

      const campaignIds = new Set(
        response.campaigns.map(
          (campaign) => campaign.campaign_id,
        ),
      );
      const adgroupIds = new Set(
        response.adgroups.map(
          (adgroup) => adgroup.adgroup_id,
        ),
      );

      setSelectedCampaignIds((current) =>
        current.filter((id) =>
          campaignIds.has(id),
        ),
      );
      setSelectedAdgroupIds((current) =>
        current.filter((id) =>
          adgroupIds.has(id),
        ),
      );
    } catch (requestError) {
      setResult(null);
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "광고 정보를 불러오지 못했습니다.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadAdvertising();
  }, []);

  if (loading) {
    return (
      <div className="empty-state">
        <span>📢</span>
        <h3>광고 정보를 불러오는 중입니다.</h3>
        <p>
          캠페인과 광고그룹 상태를 확인하고 있습니다.
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <>
        <div className="error-message">
          {error}
        </div>
        <button
          type="button"
          className="primary-button retry-button"
          onClick={() => void loadAdvertising()}
        >
          다시 불러오기
        </button>
      </>
    );
  }

  if (!result) {
    return null;
  }

  const normalizedQuery =
    campaignQuery.trim().toLocaleLowerCase();

  const filteredCampaigns =
    result.campaigns.filter((campaign) =>
      !normalizedQuery
        ? true
        : campaign.name
            .toLocaleLowerCase()
            .includes(normalizedQuery),
    );

  const selectedCampaigns =
    result.campaigns.filter((campaign) =>
      selectedCampaignIds.includes(
        campaign.campaign_id,
      ),
    );

  const availableAdgroups =
    result.adgroups.filter((adgroup) =>
      selectedCampaignIds.includes(
        adgroup.campaign_id,
      ),
    );

  const selectedAdgroups =
    result.adgroups.filter((adgroup) =>
      selectedAdgroupIds.includes(
        adgroup.adgroup_id,
      ),
    );

  const selectedActiveCampaignCount =
    selectedCampaigns.filter(
      (campaign) => campaign.status === "active",
    ).length;

  const selectedActiveAdgroupCount =
    selectedAdgroups.filter(
      (adgroup) => adgroup.status === "active",
    ).length;

  function toggleCampaign(
    campaignId: string,
  ) {
    setSelectedCampaignIds((current) => {
      if (current.includes(campaignId)) {
        setSelectedAdgroupIds(
          (currentAdgroups) =>
            currentAdgroups.filter(
              (adgroupId) => {
                const adgroup =
                  result?.adgroups.find(
                    (item) =>
                      item.adgroup_id ===
                      adgroupId,
                  );

                return (
                  adgroup?.campaign_id !==
                  campaignId
                );
              },
            ),
        );

        return current.filter(
          (id) => id !== campaignId,
        );
      }

      return [...current, campaignId];
    });
  }

  function selectFilteredCampaigns() {
    const filteredIds =
      filteredCampaigns.map(
        (campaign) => campaign.campaign_id,
      );

    setSelectedCampaignIds((current) =>
      Array.from(
        new Set([...current, ...filteredIds]),
      ),
    );
  }

  function clearCampaignSelection() {
    setSelectedCampaignIds([]);
    setSelectedAdgroupIds([]);
  }

  function toggleAdgroup(adgroupId: string) {
    setSelectedAdgroupIds((current) =>
      current.includes(adgroupId)
        ? current.filter(
            (id) => id !== adgroupId,
          )
        : [...current, adgroupId],
    );
  }

  function selectAvailableAdgroups() {
    setSelectedAdgroupIds(
      availableAdgroups.map(
        (adgroup) => adgroup.adgroup_id,
      ),
    );
  }

  return (
    <>
      <div className="advertising-toolbar">
        <span>
          전체 데이터는 최초 한 번만 불러옵니다.{" "}
          캠페인 {result.summary.campaign_count}개 ·{" "}
          광고그룹 {result.summary.adgroup_count}개 ·{" "}
          처리시간 {result.elapsed_seconds}초
        </span>

        <button
          type="button"
          className="secondary-button"
          onClick={() => void loadAdvertising()}
          disabled={loading}
        >
          서버 데이터 새로고침
        </button>
      </div>

      {result.summary.error_count > 0 && (
        <div className="error-message">
          일부 캠페인의 광고그룹을 불러오지
          못했습니다. 오류{" "}
          {result.summary.error_count}건
        </div>
      )}

      <div className="metric-grid">
        <article className="metric-card">
          <span>선택 캠페인</span>
          <strong>
            {selectedCampaigns.length}개
          </strong>
        </article>

        <article className="metric-card">
          <span>선택 캠페인 활성·중지</span>
          <strong>
            {selectedActiveCampaignCount} ·{" "}
            {selectedCampaigns.length -
              selectedActiveCampaignCount}
          </strong>
        </article>

        <article className="metric-card">
          <span>선택 광고그룹</span>
          <strong>
            {selectedAdgroups.length}개
          </strong>
        </article>

        <article className="metric-card">
          <span>선택 광고그룹 활성·중지</span>
          <strong>
            {selectedActiveAdgroupCount} ·{" "}
            {selectedAdgroups.length -
              selectedActiveAdgroupCount}
          </strong>
        </article>
      </div>

      <div className="analysis-tabs">
        <button
          type="button"
          className={
            activeTab === "campaigns"
              ? "analysis-tab active"
              : "analysis-tab"
          }
          onClick={() =>
            setActiveTab("campaigns")
          }
        >
          캠페인 선택 ({selectedCampaigns.length})
        </button>

        <button
          type="button"
          className={
            activeTab === "adgroups"
              ? "analysis-tab active"
              : "analysis-tab"
          }
          onClick={() =>
            setActiveTab("adgroups")
          }
        >
          광고그룹 선택 ({selectedAdgroups.length})
        </button>

        <button
          type="button"
          className={
            activeTab === "season"
              ? "analysis-tab active"
              : "analysis-tab"
          }
          onClick={() =>
            setActiveTab("season")
          }
        >
          시즌 분석
        </button>
      </div>

      <div
        style={{
          display:
            activeTab === "campaigns"
              ? "block"
              : "none",
        }}
      >
        <section
          style={{
            display: "grid",
            gap: "16px",
          }}
        >
          <div
            style={{
              display: "flex",
              gap: "10px",
              flexWrap: "wrap",
              alignItems: "end",
            }}
          >
            <label
              style={{
                flex: "1 1 260px",
                display: "grid",
                gap: "6px",
              }}
            >
              <span>캠페인명 검색</span>
              <input
                type="search"
                value={campaignQuery}
                onChange={(event) =>
                  setCampaignQuery(
                    event.target.value,
                  )
                }
                placeholder="캠페인명을 입력하세요"
              />
            </label>

            <button
              type="button"
              className="secondary-button"
              onClick={selectFilteredCampaigns}
              disabled={
                filteredCampaigns.length === 0
              }
            >
              검색 결과 전체 선택
            </button>

            <button
              type="button"
              className="secondary-button"
              onClick={clearCampaignSelection}
              disabled={
                selectedCampaignIds.length === 0
              }
            >
              선택 해제
            </button>
          </div>

          <div
            style={{
              maxHeight: "280px",
              overflow: "auto",
              border: "1px solid #e5e7eb",
              borderRadius: "12px",
              padding: "12px",
              display: "grid",
              gap: "8px",
            }}
          >
            {filteredCampaigns.length === 0 ? (
              <div className="empty-state compact-state">
                <span>📭</span>
                <h3>
                  검색 조건에 맞는 캠페인이 없습니다.
                </h3>
              </div>
            ) : (
              filteredCampaigns.map(
                (campaign) => (
                  <label
                    key={campaign.campaign_id}
                    style={{
                      display: "flex",
                      gap: "10px",
                      alignItems: "center",
                      padding: "8px",
                      cursor: "pointer",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={selectedCampaignIds
                        .includes(
                          campaign.campaign_id,
                        )}
                      onChange={() =>
                        toggleCampaign(
                          campaign.campaign_id,
                        )
                      }
                    />
                    <strong>{campaign.name}</strong>
                    <AdvertisingStatus
                      status={campaign.status}
                    />
                    <span>
                      {campaign.campaign_type || "-"}
                    </span>
                  </label>
                ),
              )
            )}
          </div>

          <h3>
            선택한 캠페인 ({selectedCampaigns.length})
          </h3>

          {selectedCampaigns.length === 0 ? (
            <div className="empty-state compact-state">
              <span>☝️</span>
              <h3>
                확인할 캠페인을 선택해 주세요.
              </h3>
              <p>
                선택한 캠페인만 아래 결과에 표시됩니다.
              </p>
            </div>
          ) : (
            <div className="table-scroll">
              <table className="result-table">
                <thead>
                  <tr>
                    <th>캠페인</th>
                    <th>유형</th>
                    <th>상태</th>
                    <th>일예산</th>
                    <th>수정일시</th>
                  </tr>
                </thead>

                <tbody>
                  {selectedCampaigns.map(
                    (campaign) => (
                      <tr
                        key={campaign.campaign_id}
                      >
                        <td>
                          <strong>
                            {campaign.name}
                          </strong>
                        </td>
                        <td>
                          {campaign.campaign_type ||
                            "-"}
                        </td>
                        <td>
                          <AdvertisingStatus
                            status={campaign.status}
                          />
                        </td>
                        <td>
                          {campaign.uses_daily_budget
                            ? `${campaign.daily_budget
                                .toLocaleString()}원`
                            : "제한 없음"}
                        </td>
                        <td>
                          {campaign.edited_at || "-"}
                        </td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      <div
        style={{
          display:
            activeTab === "adgroups"
              ? "block"
              : "none",
        }}
      >
        {selectedCampaigns.length === 0 ? (
          <div className="empty-state compact-state">
            <span>☝️</span>
            <h3>캠페인을 먼저 선택해 주세요.</h3>
            <p>
              캠페인 선택 탭에서 한 개 이상의
              캠페인을 선택하면 광고그룹이 표시됩니다.
            </p>
          </div>
        ) : (
          <section
            style={{
              display: "grid",
              gap: "16px",
            }}
          >
            <div
              style={{
                display: "flex",
                gap: "10px",
                flexWrap: "wrap",
                alignItems: "center",
              }}
            >
              <strong>
                선택 캠페인의 광고그룹{" "}
                {availableAdgroups.length}개
              </strong>

              <button
                type="button"
                className="secondary-button"
                onClick={selectAvailableAdgroups}
                disabled={
                  availableAdgroups.length === 0
                }
              >
                전체 선택
              </button>

              <button
                type="button"
                className="secondary-button"
                onClick={() =>
                  setSelectedAdgroupIds([])
                }
                disabled={
                  selectedAdgroupIds.length === 0
                }
              >
                선택 해제
              </button>
            </div>

            <div
              style={{
                maxHeight: "300px",
                overflow: "auto",
                border: "1px solid #e5e7eb",
                borderRadius: "12px",
                padding: "12px",
                display: "grid",
                gap: "8px",
              }}
            >
              {availableAdgroups.length === 0 ? (
                <div className="empty-state compact-state">
                  <span>📭</span>
                  <h3>
                    선택한 캠페인에 광고그룹이 없습니다.
                  </h3>
                </div>
              ) : (
                availableAdgroups.map(
                  (adgroup) => (
                    <label
                      key={adgroup.adgroup_id}
                      style={{
                        display: "flex",
                        gap: "10px",
                        alignItems: "center",
                        padding: "8px",
                        cursor: "pointer",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={selectedAdgroupIds
                          .includes(
                            adgroup.adgroup_id,
                          )}
                        onChange={() =>
                          toggleAdgroup(
                            adgroup.adgroup_id,
                          )
                        }
                      />
                      <span>
                        {adgroup.campaign_name}
                      </span>
                      <strong>
                        {adgroup.name}
                      </strong>
                      <AdvertisingStatus
                        status={adgroup.status}
                      />
                    </label>
                  ),
                )
              )}
            </div>

            <h3>
              선택한 광고그룹 ({selectedAdgroups.length})
            </h3>

            {selectedAdgroups.length === 0 ? (
              <div className="empty-state compact-state">
                <span>☝️</span>
                <h3>
                  확인할 광고그룹을 선택해 주세요.
                </h3>
                <p>
                  선택한 광고그룹만 아래 결과에 표시됩니다.
                </p>
              </div>
            ) : (
              <div className="table-scroll">
                <table className="result-table">
                  <thead>
                    <tr>
                      <th>캠페인</th>
                      <th>광고그룹</th>
                      <th>상태</th>
                      <th>입찰가</th>
                      <th>일예산</th>
                      <th>상태 사유</th>
                    </tr>
                  </thead>

                  <tbody>
                    {selectedAdgroups.map(
                      (adgroup) => (
                        <tr
                          key={adgroup.adgroup_id}
                        >
                          <td>
                            {adgroup.campaign_name}
                          </td>
                          <td>
                            <strong>
                              {adgroup.name}
                            </strong>
                          </td>
                          <td>
                            <AdvertisingStatus
                              status={adgroup.status}
                            />
                          </td>
                          <td>
                            {adgroup.bid_amount
                              .toLocaleString()}원
                          </td>
                          <td>
                            {adgroup.uses_daily_budget
                              ? `${adgroup.daily_budget
                                  .toLocaleString()}원`
                              : "제한 없음"}
                          </td>
                          <td>
                            {adgroup.status_reason ||
                              "-"}
                          </td>
                        </tr>
                      ),
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </div>

      <div
        style={{
          display:
            activeTab === "season"
              ? "block"
              : "none",
        }}
      >
        <SeasonAnalysisPanel />
      </div>
    </>
  );
}

function SeasonAnalysisPanel() {
  const [keyword, setKeyword] = useState("");
  const [months, setMonths] =
    useState<12 | 24 | 36>(24);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] =
    useState<SeasonAnalysisResponse | null>(null);

  async function handleSeasonAnalysis(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    const normalized = keyword.trim();

    if (!normalized) {
      setError("시즌을 분석할 키워드를 입력해 주세요.");
      return;
    }

    setPending(true);
    setError("");

    try {
      const response = await analyzeSeason(
        normalized,
        months,
      );
      setResult(response);
    } catch (requestError) {
      setResult(null);
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "시즌 분석 서버에 연결하지 못했습니다.",
      );
    } finally {
      setPending(false);
    }
  }

  function trendText() {
    if (!result) {
      return "-";
    }

    const change = result.summary.trend_change;
    const prefix = change > 0 ? "+" : "";

    return `${result.summary.trend_label} ${prefix}${change}`;
  }

  return (
    <section className="season-analysis">
      <form
        className="season-analysis-form"
        onSubmit={handleSeasonAnalysis}
      >
        <div className="field-group">
          <label htmlFor="season-keyword">
            분석 키워드
          </label>
          <input
            id="season-keyword"
            value={keyword}
            onChange={(event) =>
              setKeyword(event.target.value)
            }
            placeholder="예: 낚시의자"
            disabled={pending}
            required
          />
        </div>

        <div className="field-group">
          <label htmlFor="season-months">
            분석 기간
          </label>
          <select
            id="season-months"
            value={months}
            onChange={(event) =>
              setMonths(
                Number(event.target.value) as
                  | 12
                  | 24
                  | 36,
              )
            }
            disabled={pending}
          >
            <option value="12">최근 12개월</option>
            <option value="24">최근 24개월</option>
            <option value="36">최근 36개월</option>
          </select>
        </div>

        <button
          type="submit"
          className="primary-button"
          disabled={pending}
        >
          {pending
            ? "시즌 분석 중..."
            : "🌊 시즌 분석"}
        </button>
      </form>

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      {!result && !pending && (
        <div className="empty-state compact-state">
          <span>🌊</span>
          <h3>월별 검색 수요를 분석합니다.</h3>
          <p>
            키워드를 입력하면 강한 계절과 광고 준비
            시점을 확인할 수 있습니다.
          </p>
        </div>
      )}

      {result && (
        <>
          <div className="metric-grid season-metrics">
            <article className="metric-card">
              <span>월간 총 검색량</span>
              <strong>
                {result.summary.total_volume
                  .toLocaleString()}
              </strong>
            </article>

            <article className="metric-card">
              <span>최고 수요 월</span>
              <strong>
                {result.summary.peak_month}월
              </strong>
            </article>

            <article className="metric-card">
              <span>강한 계절</span>
              <strong>
                {result.summary.strongest_season}
              </strong>
            </article>

            <article className="metric-card">
              <span>최근 추세</span>
              <strong
                className={
                  `season-trend ${
                    result.summary.trend_status
                  }`
                }
              >
                {trendText()}
              </strong>
            </article>
          </div>

          <div className="season-recommendation">
            <span>💡 광고 운영 추천</span>
            <strong>
              {result.summary.recommendation}
            </strong>
            <small>
              현재 월 데이터는 집계 중일 수 있으며,
              최고 수요 계산에서는 완료된 월을 사용합니다.
            </small>
          </div>

          <div className="season-score-grid">
            {result.season_scores.map((item) => (
              <article
                className="season-score-card"
                key={item.season}
              >
                <span>{item.season}</span>
                <strong>
                  {item.average_ratio.toFixed(1)}
                </strong>
                <small>
                  평균 검색지수 · {item.sample_count}개월
                </small>
              </article>
            ))}
          </div>

          <div className="table-scroll">
            <table className="result-table season-table">
              <thead>
                <tr>
                  <th>기간</th>
                  <th>계절</th>
                  <th>검색 수요</th>
                  <th>상대 검색지수</th>
                  <th>상태</th>
                </tr>
              </thead>

              <tbody>
                {[...result.monthly]
                  .reverse()
                  .map((item) => (
                    <tr key={item.period}>
                      <td>
                        <strong>{item.period}</strong>
                      </td>
                      <td>{item.season}</td>
                      <td>
                        <div className="season-bar-track">
                          <span
                            className="season-bar"
                            style={{
                              width: `${
                                Math.max(item.ratio, 2)
                              }%`,
                            }}
                          />
                        </div>
                      </td>
                      <td>{item.ratio.toFixed(1)}</td>
                      <td>
                        {item.is_partial
                          ? "집계 중"
                          : "집계 완료"}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>

          <p className="season-source">
            네이버 데이터랩 상대 검색지수와 네이버
            검색광고 월간 검색량을 결합한 결과입니다.
            처리시간 {result.elapsed_seconds}초
            {result.cached ? " · 캐시 사용" : ""}
          </p>
        </>
      )}
    </section>
  );
}

function AdvertisingStatus({
  status,
}: {
  status: "active" | "paused";
}) {
  return (
    <span
      className={`advertising-status ${status}`}
    >
      {status === "active" ? "활성" : "중지"}
    </span>
  );
}

function RankChangeBadge({
  history,
}: {
  history?: MonitoringHistoryItem;
}) {
  if (!history) {
    return <span className="rank-change none">-</span>;
  }

  if (history.status === "up") {
    return (
      <span className="rank-change up">
        ▲ {history.rank_change}
      </span>
    );
  }

  if (history.status === "down") {
    return (
      <span className="rank-change down">
        ▼ {Math.abs(history.rank_change ?? 0)}
      </span>
    );
  }

  if (history.status === "same") {
    return (
      <span className="rank-change same">
        － 변동 없음
      </span>
    );
  }

  if (history.status === "first") {
    return (
      <span className="rank-change first">
        첫 기록
      </span>
    );
  }

  if (history.status === "not_exposed") {
    return (
      <span className="rank-change hidden">
        미노출
      </span>
    );
  }

  return (
    <span className="rank-change none">
      기록 없음
    </span>
  );
}


function DataManagement() {
  const [activeTab, setActiveTab] = useState<
    "migration" | "cache" | "system"
  >("migration");
  const [overview, setOverview] =
    useState<DataManagementOverview | null>(null);
  const [migrationResult, setMigrationResult] =
    useState<RankMigrationResponse | null>(null);
  const [cacheResult, setCacheResult] =
    useState<CacheClearResponse | null>(null);
  const [backupConfirmed, setBackupConfirmed] =
    useState(false);
  const [confirmationText, setConfirmationText] =
    useState("");
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const sheetUrl =
    process.env.NEXT_PUBLIC_GOOGLE_SHEET_URL ?? "";

  async function loadOverview() {
    setLoading(true);
    setError("");

    try {
      const response =
        await getDataManagementOverview();
      setOverview(response);
    } catch (requestError) {
      setOverview(null);
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "데이터 현황을 불러오지 못했습니다.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadOverview();
  }, []);

  async function handleMigration() {
    if (!backupConfirmed) {
      setError(
        "Google Sheets 백업 확인에 체크해 주세요.",
      );
      return;
    }

    if (confirmationText.trim() !== "통합 실행") {
      setError(
        '확인란에 "통합 실행"을 입력해 주세요.',
      );
      return;
    }

    if (
      !window.confirm(
        "기존 키워드별 순위기록을 통합하시겠습니까? " +
          "원본 워크시트는 삭제되지 않습니다.",
      )
    ) {
      return;
    }

    setPending(true);
    setError("");
    setMessage("");
    setMigrationResult(null);

    try {
      const response =
        await migrateLegacyRankSheets();
      setMigrationResult(response);
      setMessage(
        `순위기록 ${response.total_migrated_count.toLocaleString()}건을 통합했습니다.`,
      );
      setConfirmationText("");
      setBackupConfirmed(false);
      await loadOverview();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "순위기록 통합에 실패했습니다.",
      );
    } finally {
      setPending(false);
    }
  }

  async function handleClearCache() {
    if (
      !window.confirm(
        "백엔드 캐시를 초기화할까요? " +
          "Google Sheets의 실제 데이터는 삭제되지 않습니다.",
      )
    ) {
      return;
    }

    setPending(true);
    setError("");
    setMessage("");
    setCacheResult(null);

    try {
      const response =
        await clearApplicationCaches();
      setCacheResult(response);
      setMessage(response.message);
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "캐시 초기화에 실패했습니다.",
      );
    } finally {
      setPending(false);
    }
  }

  function readinessBadge(
    ready: boolean,
  ) {
    return (
      <span
        className={
          ready
            ? "system-ready"
            : "system-not-ready"
        }
      >
        {ready ? "✅ 설정됨" : "❌ 미설정"}
      </span>
    );
  }

  return (
    <section className="data-management">
      <div className="management-warning">
        <strong>⚠️ 데이터 관리 주의사항</strong>
        <p>
          순위기록 통합을 실행하기 전에 Google Sheets
          사본을 만들어 두는 것을 권장합니다. 원본 시트는
          자동으로 삭제하지 않습니다.
        </p>
      </div>

      <div className="management-toolbar">
        <button
          type="button"
          className="secondary-button"
          onClick={() => void loadOverview()}
          disabled={loading || pending}
        >
          {loading ? "현황 확인 중..." : "🔄 현황 새로고침"}
        </button>

        {sheetUrl && (
          <a
            href={sheetUrl}
            target="_blank"
            rel="noreferrer"
            className="secondary-button"
          >
            📗 Google Sheets 열기
          </a>
        )}
      </div>

      {error && (
        <div className="error-message">{error}</div>
      )}

      {message && (
        <div className="success-message">{message}</div>
      )}

      {overview && (
        <div className="metric-grid management-metrics">
          <article className="metric-card">
            <span>전체 워크시트</span>
            <strong>
              {overview.summary.worksheet_count
                .toLocaleString()}개
            </strong>
          </article>

          <article className="metric-card">
            <span>통합 순위기록</span>
            <strong>
              {overview.summary.rank_record_count
                .toLocaleString()}건
            </strong>
          </article>

          <article className="metric-card">
            <span>모니터링 항목</span>
            <strong>
              {overview.summary.monitor_count
                .toLocaleString()}개
            </strong>
          </article>

          <article className="metric-card">
            <span>원본 / 완료 / 대기</span>
            <strong>
              {overview.summary.legacy_sheet_count
                .toLocaleString()} /{" "}
              {overview.summary
                .migrated_legacy_sheet_count
                .toLocaleString()} /{" "}
              {overview.summary
                .pending_legacy_sheet_count
                .toLocaleString()}개
            </strong>
          </article>
        </div>
      )}

      {overview?.summary.latest_collected_at && (
        <div className="latest-collection-info">
          최근 순위 수집:{" "}
          <strong>
            {overview.summary.latest_collected_at}
          </strong>
        </div>
      )}

      <div className="analysis-tabs management-tabs">
        <button
          type="button"
          className={
            activeTab === "migration"
              ? "analysis-tab active"
              : "analysis-tab"
          }
          onClick={() => setActiveTab("migration")}
        >
          📦 순위기록 통합
        </button>

        <button
          type="button"
          className={
            activeTab === "cache"
              ? "analysis-tab active"
              : "analysis-tab"
          }
          onClick={() => setActiveTab("cache")}
        >
          🧹 캐시 관리
        </button>

        <button
          type="button"
          className={
            activeTab === "system"
              ? "analysis-tab active"
              : "analysis-tab"
          }
          onClick={() => setActiveTab("system")}
        >
          ℹ️ 시스템 정보
        </button>
      </div>

      {activeTab === "migration" && (
        <section className="management-panel">
          <h3>📦 기존 순위기록 통합</h3>
          <p>
            기존 키워드별 워크시트를
            <strong> 📊 통합 순위기록</strong>으로
            이전합니다. 이미 이전한 시트와 중복 기록은
            건너뜁니다.
          </p>

          {overview &&
            overview.migrated_legacy_sheets.length > 0 && (
              <div className="legacy-sheet-list">
                <strong>✅ 통합 완료·원본 보존</strong>
                <div>
                  {overview.migrated_legacy_sheets.map(
                    (sheet) => (
                      <span key={sheet}>{sheet}</span>
                    ),
                  )}
                </div>
              </div>
            )}

          {overview &&
            overview.pending_legacy_sheets.length > 0 && (
              <div className="legacy-sheet-list">
                <strong>⏳ 통합 대기 워크시트</strong>
                <div>
                  {overview.pending_legacy_sheets.map(
                    (sheet) => (
                      <span key={sheet}>{sheet}</span>
                    ),
                  )}
                </div>
              </div>
            )}

          {overview &&
            overview.pending_legacy_sheets.length === 0 && (
              <div className="success-message">
                모든 기존 순위시트가 통합되었습니다.
                원본 시트는 안전하게 보존되어 있습니다.
              </div>
            )}

          <label className="management-confirm-check">
            <input
              type="checkbox"
              checked={backupConfirmed}
              disabled={pending}
              onChange={(event) =>
                setBackupConfirmed(
                  event.target.checked,
                )
              }
            />
            Google Sheets 백업 또는 사본 생성을
            확인했습니다.
          </label>

          <div className="field-group confirmation-field">
            <label htmlFor="migration-confirmation">
              실행 확인 문구
            </label>
            <input
              id="migration-confirmation"
              value={confirmationText}
              placeholder="통합 실행"
              disabled={pending}
              onChange={(event) =>
                setConfirmationText(
                  event.target.value,
                )
              }
            />
            <small>
              실행하려면 정확히 “통합 실행”을 입력하세요.
            </small>
          </div>

          <button
            type="button"
            className="primary-button"
            disabled={
              pending ||
              !backupConfirmed ||
              confirmationText.trim() !==
                "통합 실행" ||
              !overview ||
              overview.pending_legacy_sheets.length === 0
            }
            onClick={() => void handleMigration()}
          >
            {pending
              ? "순위기록 통합 중..."
              : "🔄 기존 순위시트 통합 실행"}
          </button>

          {migrationResult && (
            <div className="migration-result">
              <div className="result-summary">
                총{" "}
                {migrationResult.total_migrated_count
                  .toLocaleString()}건 이전 · 원본 시트
                보존
              </div>

              <div className="table-scroll">
                <table className="result-table">
                  <thead>
                    <tr>
                      <th>원본 시트</th>
                      <th>이전 건수</th>
                      <th>상태</th>
                      <th>메모</th>
                    </tr>
                  </thead>
                  <tbody>
                    {migrationResult.results.map(
                      (item) => (
                        <tr key={item.source_sheet}>
                          <td>
                            <strong>
                              {item.source_sheet}
                            </strong>
                          </td>
                          <td>
                            {item.migrated_count
                              .toLocaleString()}건
                          </td>
                          <td>{item.status}</td>
                          <td>{item.message}</td>
                        </tr>
                      ),
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>
      )}

      {activeTab === "cache" && (
        <section className="management-panel">
          <h3>🧹 백엔드 캐시 관리</h3>
          <p>
            키워드 카테고리와 시즌 분석 등 임시 캐시를
            초기화합니다. Google Sheets에 저장된 실제
            데이터는 삭제하지 않습니다.
          </p>

          <button
            type="button"
            className="primary-button"
            disabled={pending}
            onClick={() => void handleClearCache()}
          >
            {pending
              ? "캐시 초기화 중..."
              : "🧹 전체 데이터 캐시 초기화"}
          </button>

          {cacheResult && (
            <div className="cache-result-grid">
              <article>
                <span>키워드 카테고리</span>
                <strong>
                  {cacheResult.cleared
                    .keyword_category_cache}개
                </strong>
              </article>
              <article>
                <span>시즌 분석</span>
                <strong>
                  {cacheResult.cleared
                    .season_analysis_cache}개
                </strong>
              </article>
              <article>
                <span>Sheets 연결</span>
                <strong>초기화 완료</strong>
              </article>
            </div>
          )}
        </section>
      )}

      {activeTab === "system" && overview && (
        <section className="management-panel">
          <h3>ℹ️ 시스템 정보</h3>

          <div className="system-info-grid">
            <article>
              <h4>현재 설정</h4>
              <dl>
                <div>
                  <dt>네이버 쇼핑 API</dt>
                  <dd>
                    {readinessBadge(
                      overview.system
                        .naver_shopping_ready,
                    )}
                  </dd>
                </div>
                <div>
                  <dt>네이버 검색광고 API</dt>
                  <dd>
                    {readinessBadge(
                      overview.system
                        .naver_search_ad_ready,
                    )}
                  </dd>
                </div>
                <div>
                  <dt>Google Sheets</dt>
                  <dd>
                    {readinessBadge(
                      overview.system
                        .google_sheets_ready,
                    )}
                  </dd>
                </div>
                <div>
                  <dt>로그인 인증</dt>
                  <dd>
                    {readinessBadge(
                      overview.system
                        .authentication_ready,
                    )}
                  </dd>
                </div>
                <div>
                  <dt>실행 환경</dt>
                  <dd>
                    {overview.system.environment}
                  </dd>
                </div>
                <div>
                  <dt>기준 시간대</dt>
                  <dd>{overview.system.timezone}</dd>
                </div>
              </dl>
            </article>

            <article>
              <h4>워크시트 목록</h4>
              <ul className="worksheet-list">
                {overview.worksheets.map(
                  (worksheet) => (
                    <li key={worksheet.title}>
                      <span>{worksheet.title}</span>
                      <small>
                        {worksheet.is_system
                          ? "시스템"
                          : "일반"}
                      </small>
                    </li>
                  ),
                )}
              </ul>
            </article>
          </div>
        </section>
      )}
    </section>
  );
}


function FeaturePreview({
  icon,
  name,
}: {
  icon: string;
  name: string;
}) {
  return (
    <div className="empty-state feature-state">
      <span>{icon}</span>
      <h3>{name} 화면 준비 완료</h3>
      <p>
        기존 Streamlit 기능을 확인하면서 같은 구성으로 순서대로
        연결합니다.
      </p>
      <div className="development-label">
        Python 백엔드 연결 예정
      </div>
    </div>
  );
}
