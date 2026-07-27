"use client";

import Image from "next/image";
import {
  FormEvent,
  Fragment,
  useEffect,
  useState,
} from "react";
import {
  ApiError,
  getAuthenticationStatus,
  loginWithPassword,
  logoutSession,
  searchRank,
  saveSelectedRankItems,
  getMonitoringList,
  updateMonitoringItem,
  deleteMonitoringItems,
  collectMonitoringRanks,
  collectSelectedMonitoringRanks,
  getMonitoringHistory,
  analyzeKeywords,
  exportKeywordAnalysisExcel,
  recommendProductNames,
  getAdvertisingOverview,
  diagnoseAdvertising,
  analyzeSeason,
  analyzeCrossPurchase,
  analyzeCandidates,
  exportCrossPurchaseAnalysisExcel,
  exportCandidateAnalysisExcel,
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
  ProductNameRecommendationResponse,
  AdvertisingOverviewResponse,
  AdvertisingDiagnosisResponse,
  SeasonAnalysisResponse,
  CrossPurchaseResponse,
  CandidateAnalysisResponse,
  DataManagementOverview,
  RankMigrationResponse,
  CacheClearResponse,
} from "@/lib/api";


function downloadExcelBlob(
  blob: Blob,
  baseName: string,
) {
  const now = new Date();
  const dateText = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("");

  const safeBaseName =
    baseName
      .replace(/[\\/:*?"<>|]/g, "-")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 100) || "분석결과";

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");

  anchor.href = url;
  anchor.download = `${safeBaseName}_${dateText}.xlsx`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();

  window.setTimeout(() => {
    URL.revokeObjectURL(url);
  }, 1000);
}

function getDownloadErrorMessage(
  error: unknown,
) {
  return error instanceof ApiError
    ? error.message
    : "엑셀 파일을 생성하지 못했습니다.";
}

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
    id: "product-name",
    icon: "✍️",
    label: "상품명 SEO 추천",
    description: "신제품 상품명을 만들거나 기존 상품명을 진단·개선합니다.",
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
          운영 시스템 정상
        </span>
        <span>순위·키워드·광고·상품 분석 기능을 이용할 수 있습니다.</span>
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

        {visitedNavigations.includes("product-name") && (
          <div
            style={{
              display:
                activeNavigation === "product-name"
                  ? "block"
                  : "none",
            }}
          >
            <ProductNameSeo />
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
        피싱템 내부 업무 시스템
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
                          className={
                            item.is_ours
                              ? "rank-market-own-row"
                              : undefined
                          }
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
                          <td>
                            <div className="rank-market-product">
                              <span>{item.title}</span>

                              {item.is_ours && (
                                <span className="our-product-badge">
                                  🎣 피싱템 상품
                                </span>
                              )}
                            </div>
                          </td>
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
  const [collecting, setCollecting] =
    useState(false);
  const [collectResult, setCollectResult] =
    useState<MonitoringCollectResponse | null>(
      null,
    );
  const [searchQuery, setSearchQuery] =
    useState("");
  const [statusFilter, setStatusFilter] =
    useState<
      | "all"
      | "exposed"
      | "not_exposed"
      | "no_history"
      | "error"
    >("all");
  const [sortOption, setSortOption] =
    useState<
      | "rank_asc"
      | "change_desc"
      | "keyword"
      | "registered_desc"
    >("rank_asc");
  const [expandedIds, setExpandedIds] =
    useState<string[]>([]);
  const [editingItem, setEditingItem] =
    useState<MonitorItem | null>(null);

  async function loadItems(
    resetSelection = true,
  ) {
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

      if (resetSelection) {
        setSelectedIds([]);
      }
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
      const result =
        await deleteMonitoringItems(selectedIds);

      await loadItems();
      setMessage(result.message);
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

  async function handleCollect(
    itemIds?: string[],
  ) {
    if (itemIds && itemIds.length === 0) {
      setError(
        "순위를 수집할 항목을 선택해 주세요.",
      );
      return;
    }

    setCollecting(true);
    setMessage("");
    setError("");
    setCollectResult(null);

    try {
      const result = itemIds
        ? await collectSelectedMonitoringRanks(
            itemIds,
          )
        : await collectMonitoringRanks();

      setCollectResult(result);
      await loadItems(false);
      setMessage(
        itemIds
          ? `선택한 ${result.total_items}개 항목의 순위 수집을 완료했습니다.`
          : `전체 ${result.total_items}개 항목의 순위 수집을 완료했습니다.`,
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

  async function handleUpdate(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    if (!editingItem) {
      return;
    }

    const formData = new FormData(
      event.currentTarget,
    );

    setActionPending(true);
    setMessage("");
    setError("");

    try {
      const result =
        await updateMonitoringItem({
          item_id: editingItem.item_id,
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

      await loadItems(false);
      setEditingItem(null);
      setMessage(result.message);
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "모니터링 항목을 수정하지 못했습니다.",
      );
    } finally {
      setActionPending(false);
    }
  }

  function toggleSelection(itemId: string) {
    setSelectedIds((current) =>
      current.includes(itemId)
        ? current.filter((id) => id !== itemId)
        : [...current, itemId],
    );
  }

  function itemStatus(item: MonitorItem) {
    const collectItem =
      collectResult?.results.find(
        (result) =>
          result.item_id === item.item_id,
      );

    if (collectItem?.status === "error") {
      return "error";
    }

    const history = historyById[item.item_id];

    if (
      !history ||
      history.status === "no_history"
    ) {
      return "no_history";
    }

    if (history.latest_rank === null) {
      return "not_exposed";
    }

    return "exposed";
  }

  function rankStatus(rank: number | null) {
    if (!rank) {
      return {
        label: "⚪ 미노출",
        background: "#f3f4f6",
        color: "#4b5563",
      };
    }

    if (rank <= 10) {
      return {
        label: "🟢 TOP 10",
        background: "#dcfce7",
        color: "#166534",
      };
    }

    if (rank <= 50) {
      return {
        label: "🟢 TOP 50",
        background: "#ecfdf5",
        color: "#047857",
      };
    }

    if (rank <= 100) {
      return {
        label: "🟡 TOP 100",
        background: "#fef9c3",
        color: "#854d0e",
      };
    }

    if (rank <= 200) {
      return {
        label: "🟠 TOP 200",
        background: "#ffedd5",
        color: "#9a3412",
      };
    }

    return {
      label: "🔴 200위 밖",
      background: "#fee2e2",
      color: "#991b1b",
    };
  }

  function rankChangeText(
    history:
      | MonitoringHistoryItem
      | undefined,
  ) {
    if (!history) {
      return "➖ 기록 없음";
    }

    if (
      history.latest_rank === null &&
      history.status === "not_exposed"
    ) {
      return "➖ 미노출";
    }

    if (
      history.rank_change === null ||
      history.previous_rank === null
    ) {
      return "➖ 첫 기록";
    }

    if (history.rank_change > 0) {
      return `🔺 ${history.rank_change}위 상승`;
    }

    if (history.rank_change < 0) {
      return `🔻 ${Math.abs(
        history.rank_change,
      )}위 하락`;
    }

    return "➖ 변동 없음";
  }

  function toggleExpanded(itemId: string) {
    setExpandedIds((current) =>
      current.includes(itemId)
        ? current.filter((id) => id !== itemId)
        : [...current, itemId],
    );
  }

  const normalizedQuery =
    searchQuery.trim().toLocaleLowerCase();

  const filteredItems = [...items]
    .filter((item) => {
      const status = itemStatus(item);

      if (
        statusFilter !== "all" &&
        status !== statusFilter
      ) {
        return false;
      }

      if (!normalizedQuery) {
        return true;
      }

      return [
        item.keyword,
        item.product_name,
        item.product_id,
        item.memo,
      ].some((value) =>
        String(value || "")
          .toLocaleLowerCase()
          .includes(normalizedQuery),
      );
    })
    .sort((left, right) => {
      const leftHistory =
        historyById[left.item_id];
      const rightHistory =
        historyById[right.item_id];

      if (sortOption === "rank_asc") {
        return (
          (leftHistory?.latest_rank ??
            Number.MAX_SAFE_INTEGER) -
          (rightHistory?.latest_rank ??
            Number.MAX_SAFE_INTEGER)
        );
      }

      if (sortOption === "change_desc") {
        return (
          Math.abs(
            rightHistory?.rank_change ?? 0,
          ) -
          Math.abs(
            leftHistory?.rank_change ?? 0,
          )
        );
      }

      if (sortOption === "keyword") {
        return left.keyword.localeCompare(
          right.keyword,
          "ko",
        );
      }

      return String(
        right.registered_at || "",
      ).localeCompare(
        String(left.registered_at || ""),
      );
    });

  const statusCounts = items.reduce(
    (counts, item) => {
      const status = itemStatus(item);
      counts[status] += 1;
      return counts;
    },
    {
      exposed: 0,
      not_exposed: 0,
      no_history: 0,
      error: 0,
    },
  );

  const visibleIds = filteredItems.map(
    (item) => item.item_id,
  );

  const allVisibleSelected =
    visibleIds.length > 0 &&
    visibleIds.every((id) =>
      selectedIds.includes(id),
    );

  function toggleAllVisible() {
    setSelectedIds((current) => {
      if (allVisibleSelected) {
        return current.filter(
          (id) => !visibleIds.includes(id),
        );
      }

      return Array.from(
        new Set([...current, ...visibleIds]),
      );
    });
  }

  return (
    <>

      {editingItem && (
        <form
          id="monitoring-edit-form"
          className="monitoring-edit-form"
          onSubmit={handleUpdate}
          style={{
            margin: "18px 0",
            padding: "18px",
            border: "2px solid #bfdbfe",
            borderRadius: "14px",
            background: "#eff6ff",
            display: "grid",
            gap: "14px",
          }}
        >
          <div>
            <strong>
              ✏️ 모니터링 항목 수정
            </strong>
            <p
              style={{
                margin: "5px 0 0",
              }}
            >
              등록일과 항목 ID는 그대로 유지됩니다.
            </p>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit, minmax(210px, 1fr))",
              gap: "12px",
            }}
          >
            <label>
              키워드
              <input
                name="keyword"
                type="text"
                defaultValue={
                  editingItem.keyword
                }
                disabled={actionPending}
                required
              />
            </label>

            <label>
              메모
              <input
                name="memo"
                type="text"
                defaultValue={editingItem.memo}
                disabled={actionPending}
              />
            </label>

            <label>
              productId
              <input
                name="product_id"
                type="text"
                defaultValue={
                  editingItem.product_id
                }
                disabled={actionPending}
              />
            </label>

            <label>
              상품명
              <input
                name="product_name"
                type="text"
                defaultValue={
                  editingItem.product_name
                }
                disabled={actionPending}
              />
            </label>
          </div>

          <div
            style={{
              display: "flex",
              gap: "10px",
              flexWrap: "wrap",
            }}
          >
            <button
              type="submit"
              className="primary-button"
              disabled={actionPending}
            >
              {actionPending
                ? "수정 저장 중..."
                : "수정 내용 저장"}
            </button>

            <button
              type="button"
              className="secondary-button"
              onClick={() =>
                setEditingItem(null)
              }
              disabled={actionPending}
            >
              취소
            </button>
          </div>
        </form>
      )}

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

      <div className="metric-grid">
        <article className="metric-card">
          <span>전체 항목</span>
          <strong>{items.length}개</strong>
        </article>

        <article className="metric-card">
          <span>현재 노출</span>
          <strong>
            {statusCounts.exposed}개
          </strong>
        </article>

        <article className="metric-card">
          <span>미노출</span>
          <strong>
            {statusCounts.not_exposed}개
          </strong>
        </article>

        <article className="metric-card">
          <span>기록 없음·오류</span>
          <strong>
            {statusCounts.no_history} ·{" "}
            {statusCounts.error}
          </strong>
        </article>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns:
            "minmax(220px, 1fr) 180px 210px",
          gap: "10px",
          margin: "18px 0",
        }}
      >
        <label>
          목록 검색
          <input
            type="search"
            value={searchQuery}
            onChange={(event) =>
              setSearchQuery(event.target.value)
            }
            placeholder="키워드·상품명·메모 검색"
          />
        </label>

        <label>
          상태
          <select
            value={statusFilter}
            onChange={(event) =>
              setStatusFilter(
                event.target.value as
                  | "all"
                  | "exposed"
                  | "not_exposed"
                  | "no_history"
                  | "error",
              )
            }
          >
            <option value="all">전체 상태</option>
            <option value="exposed">노출</option>
            <option value="not_exposed">
              미노출
            </option>
            <option value="no_history">
              수집 기록 없음
            </option>
            <option value="error">오류</option>
          </select>
        </label>

        <label>
          정렬
          <select
            value={sortOption}
            onChange={(event) =>
              setSortOption(
                event.target.value as
                  | "rank_asc"
                  | "change_desc"
                  | "keyword"
                  | "registered_desc",
              )
            }
          >
            <option value="rank_asc">
              순위 높은 순
            </option>
            <option value="change_desc">
              변동 큰 순
            </option>
            <option value="keyword">
              키워드 가나다순
            </option>
            <option value="registered_desc">
              최근 등록순
            </option>
          </select>
        </label>
      </div>

      <div className="monitoring-toolbar">
        <strong>
          표시 {filteredItems.length}개 · 선택{" "}
          {selectedIds.length}개
        </strong>

        <button
          type="button"
          className="primary-button"
          onClick={() =>
            void handleCollect(selectedIds)
          }
          disabled={
            loading ||
            actionPending ||
            collecting ||
            selectedIds.length === 0
          }
        >
          {collecting
            ? "순위 수집 중..."
            : `🎯 선택 ${selectedIds.length}개 수집`}
        </button>

        <button
          type="button"
          className="secondary-button"
          onClick={() => void handleCollect()}
          disabled={
            loading ||
            actionPending ||
            collecting ||
            items.length === 0
          }
        >
          {collecting
            ? "순위 수집 중..."
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
          className="danger-button"
          onClick={() => void handleDelete()}
          disabled={
            actionPending ||
            selectedIds.length === 0
          }
        >
          선택 삭제 ({selectedIds.length})
        </button>
      </div>

      {collectResult && (
        <details
          open
          style={{
            margin: "16px 0",
          }}
        >
          <summary
            style={{
              cursor: "pointer",
              fontWeight: 800,
            }}
          >
            최근 수집 결과 자세히 보기
          </summary>

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
        </details>
      )}

      {loading ? (
        <div className="empty-state">
          <span>⏳</span>
          <h3>
            모니터링 목록을 불러오는 중입니다.
          </h3>
        </div>
      ) : items.length === 0 ? (
        <div className="empty-state">
          <span>📋</span>
          <h3>
            등록된 모니터링 항목이 없습니다.
          </h3>
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="empty-state">
          <span>🔎</span>
          <h3>
            검색·필터 조건에 맞는 항목이 없습니다.
          </h3>
          <p>
            검색어 또는 상태 필터를 변경해 주세요.
          </p>
        </div>
      ) : (
        <div className="table-scroll monitoring-table-scroll">
          <table className="result-table monitoring-result-table">
            <thead>
              <tr>
                <th>
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    onChange={toggleAllVisible}
                    aria-label="표시 항목 전체 선택"
                  />
                </th>
                <th>키워드·상품</th>
                <th>최신 순위</th>
                <th>순위 상태</th>
                <th>순위 변화</th>
                <th>마지막 수집</th>
                <th>메모</th>
                <th>등록일</th>
                <th>관리</th>
              </tr>
            </thead>

            <tbody>
              {filteredItems.map((item) => {
                const history =
                  historyById[item.item_id];
                const status = itemStatus(item);
                const rank =
                  history?.latest_rank ?? null;
                const presentation =
                  rankStatus(rank);
                const displayTitle =
                  item.product_name ||
                  history?.latest_title ||
                  "전체 피싱템 상품";
                const imageUrl =
                  history?.latest_image &&
                  /^https?:\/\//i.test(
                    history.latest_image,
                  )
                    ? history.latest_image
                    : "";
                const productLink =
                  history?.latest_link &&
                  /^https?:\/\//i.test(
                    history.latest_link,
                  )
                    ? history.latest_link
                    : "";
                const recentHistory =
                  history?.recent_history ?? [];
                const expanded =
                  expandedIds.includes(
                    item.item_id,
                  );

                return (
                  <Fragment key={item.item_id}>
                    <tr>
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(
                          item.item_id,
                        )}
                        onChange={() =>
                          toggleSelection(
                            item.item_id,
                          )
                        }
                        aria-label={`${item.keyword} 선택`}
                      />
                    </td>

                    <td>
                      <div
                        style={{
                          display: "flex",
                          gap: "12px",
                          alignItems: "center",
                          minWidth: "270px",
                        }}
                      >
                        {imageUrl ? (
                          <img
                            src={imageUrl}
                            alt={displayTitle}
                            width={64}
                            height={64}
                            loading="lazy"
                            referrerPolicy="no-referrer"
                            style={{
                              width: "64px",
                              height: "64px",
                              objectFit: "cover",
                              borderRadius: "10px",
                              border:
                                "1px solid #e5e7eb",
                              flexShrink: 0,
                            }}
                          />
                        ) : (
                          <div
                            aria-hidden="true"
                            style={{
                              width: "64px",
                              height: "64px",
                              display: "grid",
                              placeItems: "center",
                              borderRadius: "10px",
                              background: "#f3f4f6",
                              flexShrink: 0,
                            }}
                          >
                            🎣
                          </div>
                        )}

                        <div>
                          <strong>
                            {item.keyword}
                          </strong>

                          <div>
                            {productLink ? (
                              <a
                                href={productLink}
                                target="_blank"
                                rel="noreferrer"
                                style={{
                                  color: "#0066cc",
                                  fontWeight: 700,
                                }}
                              >
                                {displayTitle} ↗
                              </a>
                            ) : (
                              displayTitle
                            )}
                          </div>

                          {(history?.latest_mall_name ||
                            history?.latest_price >
                              0) && (
                            <small>
                              {history
                                ?.latest_mall_name ||
                                "판매처 확인 불가"}
                              {history?.latest_price >
                                0
                                ? ` · ${history.latest_price.toLocaleString()}원`
                                : ""}
                            </small>
                          )}

                          <div>
                            <button
                              type="button"
                              className="secondary-button"
                              onClick={() =>
                                toggleExpanded(
                                  item.item_id,
                                )
                              }
                              style={{
                                marginTop: "7px",
                                padding: "5px 9px",
                                minHeight: "auto",
                              }}
                            >
                              {expanded
                                ? "이력 닫기"
                                : "최근 순위 보기"}
                            </button>
                          </div>
                        </div>
                      </div>
                    </td>

                    <td>
                      <strong>
                        {rank ? `${rank}위` : "-"}
                      </strong>
                    </td>

                    <td>
                      {status === "error" ? (
                        <span
                          style={{
                            display: "inline-block",
                            borderRadius: "999px",
                            padding: "5px 9px",
                            background: "#fee2e2",
                            color: "#991b1b",
                            fontWeight: 800,
                            whiteSpace: "nowrap",
                          }}
                        >
                          ⚠️ 수집 오류
                        </span>
                      ) : status ===
                        "no_history" ? (
                        <span
                          style={{
                            display: "inline-block",
                            borderRadius: "999px",
                            padding: "5px 9px",
                            background: "#f3f4f6",
                            color: "#4b5563",
                            fontWeight: 800,
                            whiteSpace: "nowrap",
                          }}
                        >
                          ➖ 기록 없음
                        </span>
                      ) : (
                        <span
                          style={{
                            display: "inline-block",
                            borderRadius: "999px",
                            padding: "5px 9px",
                            background:
                              presentation.background,
                            color:
                              presentation.color,
                            fontWeight: 800,
                            whiteSpace: "nowrap",
                          }}
                        >
                          {presentation.label}
                        </span>
                      )}
                    </td>

                    <td>
                      {rankChangeText(history)}
                    </td>

                    <td>
                      {history?.latest_collected_at ||
                        "-"}
                    </td>

                    <td>{item.memo || "-"}</td>

                    <td>
                      {item.registered_at || "-"}
                    </td>

                    <td>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => {
                          setEditingItem(item);

                          window.setTimeout(() => {
                            document
                              .getElementById(
                                "monitoring-edit-form",
                              )
                              ?.scrollIntoView({
                                behavior: "smooth",
                                block: "center",
                              });
                          }, 0);
                        }}
                        disabled={actionPending}
                        style={{
                          padding: "6px 10px",
                          minHeight: "auto",
                        }}
                      >
                        수정
                      </button>
                    </td>
                  </tr>

                  {expanded && (
                    <tr
                      key={`${item.item_id}-history`}
                    >
                      <td
                        colSpan={9}
                        style={{
                          background: "#f8fafc",
                          padding: "16px",
                        }}
                      >
                        <div
                          style={{
                            display: "grid",
                            gap: "12px",
                          }}
                        >
                          <strong>
                            최근 순위 이력
                          </strong>

                          {recentHistory.length ===
                          0 ? (
                            <span>
                              아직 수집된 순위 기록이
                              없습니다.
                            </span>
                          ) : (
                            <div
                              style={{
                                display: "flex",
                                gap: "8px",
                                flexWrap: "wrap",
                              }}
                            >
                              {recentHistory.map(
                                (entry, index) => (
                                  <div
                                    key={
                                      `${entry.collected_at}-` +
                                      `${index}`
                                    }
                                    style={{
                                      minWidth: "130px",
                                      border:
                                        "1px solid #e5e7eb",
                                      borderRadius:
                                        "10px",
                                      background:
                                        "#ffffff",
                                      padding:
                                        "10px 12px",
                                    }}
                                  >
                                    <strong>
                                      {entry.rank
                                        ? `${entry.rank}위`
                                        : "미노출"}
                                    </strong>
                                    <div>
                                      <small>
                                        {entry
                                          .collected_at ||
                                          "-"}
                                      </small>
                                    </div>
                                  </div>
                                ),
                              )}
                            </div>
                          )}

                          <div
                            style={{
                              display: "flex",
                              gap: "14px",
                              flexWrap: "wrap",
                            }}
                          >
                            {productLink && (
                              <a
                                href={productLink}
                                target="_blank"
                                rel="noreferrer"
                                className="secondary-button"
                              >
                                상품 페이지 열기
                              </a>
                            )}

                            {item.product_id && (
                              <span>
                                productId:{" "}
                                <strong>
                                  {item.product_id}
                                </strong>
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function ProductNameSeo() {
  const [mainKeyword, setMainKeyword] =
    useState("");
  const [productType, setProductType] =
    useState("");
  const [brand, setBrand] =
    useState("피싱템");
  const [modelName, setModelName] =
    useState("");
  const [featuresText, setFeaturesText] =
    useState("");
  const [
    requiredWordsText,
    setRequiredWordsText,
  ] = useState("");
  const [
    excludedWordsText,
    setExcludedWordsText,
  ] = useState("");
  const [currentTitle, setCurrentTitle] =
    useState("");
  const [analysisPending, setAnalysisPending] =
    useState(false);
  const [message, setMessage] =
    useState("");
  const [error, setError] =
    useState("");
  const [copiedTitle, setCopiedTitle] =
    useState("");
  const [result, setResult] =
    useState<ProductNameRecommendationResponse | null>(
      null,
    );

  function splitWords(value: string) {
    return value
      .split(/[,/\n]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function resetResult() {
    setResult(null);
    setError("");
    setMessage("");
    setCopiedTitle("");
  }

  async function handleRecommend(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    const resolvedKeyword = mainKeyword.trim();
    const resolvedTitle = currentTitle.trim();
    const requestMode =
      resolvedTitle ? "existing" : "new";

    if (!resolvedKeyword) {
      setError("메인 키워드를 입력해 주세요.");
      return;
    }

    if (!productType.trim()) {
      setError("제품 종류를 입력해 주세요.");
      return;
    }

    setAnalysisPending(true);
    setError("");
    setMessage("");
    setResult(null);

    try {
      const response =
        await recommendProductNames({
          mode: requestMode,
          main_keyword: resolvedKeyword,
          product_type: productType.trim(),
          brand: brand.trim() || "피싱템",
          model_name: modelName.trim(),
          features: splitWords(featuresText),
          required_words:
            splitWords(requiredWordsText),
          excluded_words:
            splitWords(excludedWordsText),
          current_title: resolvedTitle,
          product_url: "",
        });

      setResult(response);
      setMessage(
        resolvedTitle
          ? "현재 상품명 진단과 SEO 추천을 완료했습니다."
          : "SEO 상품명 추천을 완료했습니다.",
      );
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : requestError instanceof Error
            ? requestError.message
            : "상품명 추천을 완료하지 못했습니다.",
      );
    } finally {
      setAnalysisPending(false);
    }
  }

  async function copyTitle(title: string) {
    try {
      await navigator.clipboard.writeText(
        title,
      );
      setCopiedTitle(title);
      setMessage(
        "추천 상품명을 클립보드에 복사했습니다.",
      );
    } catch {
      setError(
        "상품명을 복사하지 못했습니다.",
      );
    }
  }

  return (
    <div className="product-name-seo">
      <form
        className="product-name-form"
        onSubmit={handleRecommend}
      >
        <section className="product-name-link-box">
          <div className="field-group">
            <label htmlFor="seo-current-title">
              현재 상품명 (선택)
            </label>
            <input
              id="seo-current-title"
              type="text"
              value={currentTitle}
              onChange={(event) => {
                setCurrentTitle(event.target.value);
                resetResult();
              }}
              placeholder="기존 상품을 개선할 때만 현재 상품명을 붙여 넣으세요"
            />
            <small>
              비워두면 신규 상품명 추천으로 작동합니다.
              현재 상품명을 입력하면 유지·삭제·추가 단어와
              변경 전후를 함께 진단합니다.
            </small>
          </div>
        </section>

            <section className="product-name-basic-grid">
              <div className="field-group">
                <label htmlFor="seo-main-keyword">
                  메인 키워드 *
                </label>
                <input
                  id="seo-main-keyword"
                  value={mainKeyword}
                  onChange={(event) =>
                    setMainKeyword(
                      event.target.value,
                    )
                  }
                  placeholder="예: 낚시의자"
                  required
                />
              </div>

              <div className="field-group">
                <label htmlFor="seo-product-type">
                  제품 종류 *
                </label>
                <input
                  id="seo-product-type"
                  value={productType}
                  onChange={(event) =>
                    setProductType(
                      event.target.value,
                    )
                  }
                  placeholder="예: 접이식 낚시의자"
                  required
                />
              </div>

              <div className="field-group">
                <label htmlFor="seo-brand">
                  브랜드
                </label>
                <input
                  id="seo-brand"
                  value={brand}
                  onChange={(event) =>
                    setBrand(
                      event.target.value,
                    )
                  }
                  placeholder="피싱템"
                />
              </div>
            </section>

            <div className="field-group">
              <label htmlFor="seo-features">
                제품 특징
              </label>
              <input
                id="seo-features"
                value={featuresText}
                onChange={(event) =>
                  setFeaturesText(
                    event.target.value,
                  )
                }
                placeholder="접이식, 경량, 등받이, 휴대용"
              />
              <small>
                실제 제품에 해당하는 특징만 쉼표로
                구분해 입력하세요.
              </small>
            </div>

            <details className="product-name-advanced">
              <summary>
                상세 정보 더 입력하기
              </summary>

              <div className="product-name-basic-grid">
                <div className="field-group">
                  <label htmlFor="seo-model-name">
                    모델명·품번
                  </label>
                  <input
                    id="seo-model-name"
                    value={modelName}
                    onChange={(event) =>
                      setModelName(
                        event.target.value,
                      )
                    }
                    placeholder="예: FT-CHAIR-01"
                  />
                </div>

                <div className="field-group">
                  <label htmlFor="seo-required">
                    반드시 포함할 단어
                  </label>
                  <input
                    id="seo-required"
                    value={requiredWordsText}
                    onChange={(event) =>
                      setRequiredWordsText(
                        event.target.value,
                      )
                    }
                    placeholder="민물낚시, 바다낚시"
                  />
                </div>

                <div className="field-group">
                  <label htmlFor="seo-excluded">
                    제외할 단어
                  </label>
                  <input
                    id="seo-excluded"
                    value={excludedWordsText}
                    onChange={(event) =>
                      setExcludedWordsText(
                        event.target.value,
                      )
                    }
                    placeholder="캠핑, 의자세트"
                  />
                </div>
              </div>
            </details>
        <div className="product-name-submit-row">
          <button
            type="submit"
            className="primary-button"
              disabled={analysisPending}
            >
              {analysisPending
                ? "키워드·경쟁상품 분석 중..."
                : "🔍 상품명 분석 및 추천"}
          </button>

          {result && (
            <button
              type="button"
              className="secondary-button"
              onClick={resetResult}
            >
              결과 초기화
            </button>
          )}
        </div>
      </form>

      {message && (
        <div className="info-message">
          {message}
        </div>
      )}

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      {analysisPending && (
        <div className="empty-state">
          <div className="loading-spinner" />
          <strong>
            검색량과 경쟁상품을 분석하고 있습니다.
          </strong>
          <p>
            네이버 API 응답에 따라 시간이 걸릴 수
            있습니다.
          </p>
        </div>
      )}

      {result && !analysisPending && (
        <div className="product-name-results">
          <section className="product-name-summary">
            <div>
              <span>메인 키워드</span>
              <strong>
                {result.main_keyword}
              </strong>
            </div>
            <div>
              <span>대표 카테고리</span>
              <strong>
                {result.representative_category
                  || "확인되지 않음"}
              </strong>
            </div>
            <div>
              <span>분석 경쟁상품</span>
              <strong>
                {result.competitor_titles.length}개
              </strong>
            </div>
          </section>

          {result.current_title && (
            <section className="product-name-current">
              <p className="eyebrow">
                CURRENT PRODUCT NAME
              </p>
              <h3>현재 상품명</h3>
              <p className="product-name-current-title">
                {result.current_title}
              </p>

              {result.current_title_warnings.length > 0 && (
                <ul className="product-name-warning-list">
                  {result.current_title_warnings.map(
                    (warning) => (
                      <li key={warning}>
                        {warning}
                      </li>
                    ),
                  )}
                </ul>
              )}

              <div className="product-name-diagnosis">
                {result.current_title_diagnosis.keep.length > 0 && (
                  <div>
                    <strong>유지 권장</strong>
                    <span>
                      {result.current_title_diagnosis.keep.join(", ")}
                    </span>
                  </div>
                )}
                {result.current_title_diagnosis.remove.length > 0 && (
                  <div>
                    <strong className="removed">삭제 권장</strong>
                    <span>
                      {result.current_title_diagnosis.remove.join(", ")}
                    </span>
                  </div>
                )}
                {result.current_title_diagnosis.consider.length > 0 && (
                  <div>
                    <strong className="added">추가 검토</strong>
                    <span>
                      {result.current_title_diagnosis.consider.join(", ")}
                    </span>
                  </div>
                )}
              </div>
            </section>
          )}

          <section>
            <div className="section-heading-row">
              <div>
                <p className="eyebrow">
                  RECOMMENDED PRODUCT NAMES
                </p>
                <h3>추천 상품명</h3>
              </div>
              <span className="status-badge">
                검토 후 스마트스토어에 적용
              </span>
            </div>

            <div className="product-name-candidate-grid">
              {result.candidates.map(
                (candidate, index) => (
                  <article
                    key={candidate.title}
                    className={
                      index === 0
                        ? "product-name-candidate recommended"
                        : "product-name-candidate"
                    }
                  >
                    <div className="product-name-candidate-head">
                      <div>
                        <span className="product-name-style">
                          {candidate.style}
                        </span>
                        {index === 0 && (
                          <span className="product-name-best">
                            최종 권장
                          </span>
                        )}
                      </div>
                      <strong>
                        SEO {candidate.score}점
                      </strong>
                    </div>

                    <h4>{candidate.title}</h4>

                    <div className="product-name-meta">
                      <span>
                        {candidate.length}자
                      </span>
                      <span>
                        키워드{" "}
                        {candidate.used_keywords.length}개
                      </span>
                    </div>

                    <div className="product-name-score-grid">
                      <span>
                        메인 키워드
                        <strong>{candidate.score_breakdown.main_keyword}/25</strong>
                      </span>
                      <span>
                        제품 적합성
                        <strong>{candidate.score_breakdown.product_relevance}/20</strong>
                      </span>
                      <span>
                        검색 수요
                        <strong>{candidate.score_breakdown.search_demand}/15</strong>
                      </span>
                      <span>
                        경쟁상품 반영
                        <strong>{candidate.score_breakdown.competitor_usage}/15</strong>
                      </span>
                      <span>
                        카테고리
                        <strong>{candidate.score_breakdown.category_fit}/10</strong>
                      </span>
                      <span>
                        가독성
                        <strong>{candidate.score_breakdown.readability}/10</strong>
                      </span>
                      <span>
                        기준 준수
                        <strong>{candidate.score_breakdown.policy_compliance}/5</strong>
                      </span>
                    </div>

                    <p>{candidate.reason}</p>

                    <div className="product-name-keyword-chips">
                      {candidate.used_keywords.map(
                        (keyword) => (
                          <span key={keyword}>
                            #{keyword.replace(/\s+/g, "")}
                          </span>
                        ),
                      )}
                    </div>

                    {result.mode === "existing" && (
                      <div className="product-name-diff">
                        {candidate.changes.kept.length > 0 && (
                          <p>
                            <strong>유지</strong>
                            {candidate.changes.kept.join(
                              ", ",
                            )}
                          </p>
                        )}
                        {candidate.changes.added.length > 0 && (
                          <p>
                            <strong className="added">
                              추가
                            </strong>
                            {candidate.changes.added.join(
                              ", ",
                            )}
                          </p>
                        )}
                        {candidate.changes.removed.length > 0 && (
                          <p>
                            <strong className="removed">
                              삭제
                            </strong>
                            {candidate.changes.removed.join(
                              ", ",
                            )}
                          </p>
                        )}
                      </div>
                    )}

                    {candidate.warnings.length > 0 && (
                      <ul className="product-name-warning-list">
                        {candidate.warnings.map(
                          (warning) => (
                            <li key={warning}>
                              {warning}
                            </li>
                          ),
                        )}
                      </ul>
                    )}

                    <button
                      type="button"
                      className="primary-button product-name-copy"
                      onClick={() =>
                        void copyTitle(
                          candidate.title,
                        )
                      }
                    >
                      {copiedTitle === candidate.title
                        ? "✓ 복사 완료"
                        : "📋 상품명 복사"}
                    </button>
                  </article>
                ),
              )}
            </div>
          </section>

          {result.competitor_terms.length > 0 && (
            <section className="product-name-data-section">
              <div>
                <p className="eyebrow">
                  TOP 10 WORD ANALYSIS
                </p>
                <h3>경쟁상품 핵심 단어</h3>
                <p className="section-description">
                  네이버 쇼핑 TOP 10 상품명에서 반복된 단어입니다.
                  실제 제품에 해당하는 단어만 추천명에 반영됩니다.
                </p>
              </div>

              <div className="product-name-market-terms">
                {result.competitor_terms.map((item) => (
                  <div key={item.term}>
                    <strong>{item.term}</strong>
                    <span>
                      {item.product_count}개 상품 · {item.frequency}%
                    </span>
                    <em>{item.recommendation}</em>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="product-name-data-section">
            <div>
              <p className="eyebrow">
                KEYWORD DATA
              </p>
              <h3>추천 키워드 검색량</h3>
            </div>

            <div className="table-scroll">
              <table className="result-table">
                <thead>
                  <tr>
                    <th>키워드</th>
                    <th>총 검색량</th>
                    <th>경쟁도</th>
                    <th>대표 카테고리</th>
                  </tr>
                </thead>
                <tbody>
                  {result.keyword_suggestions.map(
                    (item) => (
                      <tr key={item.keyword}>
                        <td>
                          <strong>
                            {item.keyword}
                          </strong>
                        </td>
                        <td>
                          {item.total_volume.toLocaleString()}
                        </td>
                        <td>
                          {item.competition || "-"}
                        </td>
                        <td>
                          {item.representative_category
                            || "-"}
                        </td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <details className="product-name-competitors">
            <summary>
              시장 경쟁상품 TOP 10 확인
            </summary>

            <div className="table-scroll">
              <table className="result-table">
                <thead>
                  <tr>
                    <th>순위</th>
                    <th>상품명</th>
                    <th>판매처</th>
                  </tr>
                </thead>
                <tbody>
                  {result.competitor_titles.map(
                    (item) => (
                      <tr
                        key={`${item.rank}-${item.title}`}
                      >
                        <td>{item.rank}</td>
                        <td>{item.title}</td>
                        <td>{item.mall_name}</td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            </div>
          </details>

          <div className="product-name-notice">
            상품명 추천은 검색 적합성을 높이기 위한
            참고 자료이며 상위 노출을 보장하지 않습니다.
            실제 상품과 일치하는 정보만 사용하세요.
          </div>
        </div>
      )}
    </div>
  );
}

function KeywordAnalysis() {
  const [keyword, setKeyword] = useState("");
  const [relatedLimit, setRelatedLimit] =
    useState<10 | 20 | 30 | 50 | 100>(20);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] =
    useState<KeywordAnalysisResponse | null>(null);
  const [excelPending, setExcelPending] =
    useState(false);

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

  async function handleExcelDownload() {
    if (!result || excelPending) {
      return;
    }

    setExcelPending(true);
    setError("");

    try {
      const blob =
        await exportKeywordAnalysisExcel(
          result.keyword,
          result.keywords,
        );

      const url = URL.createObjectURL(blob);
      const anchor =
        document.createElement("a");
      const safeKeyword = result.keyword
        .replace(/[\\/:*?"<>|]/g, "_")
        .slice(0, 50);
      const timestamp = new Date()
        .toISOString()
        .replace(/[-:T]/g, "")
        .slice(0, 14);

      anchor.href = url;
      anchor.download =
        `키워드분석_${safeKeyword}_${timestamp}.xlsx`;

      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "엑셀 파일을 만들지 못했습니다.",
      );
    } finally {
      setExcelPending(false);
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
                  | 30
                  | 50
                  | 100,
              )
            }
            disabled={pending}
          >
            <option value="10">10개</option>
            <option value="20">20개</option>
            <option value="30">30개</option>
            <option value="50">50개</option>
            <option value="100">100개</option>
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

          <section className="keyword-hashtag-panel">
            <div className="keyword-hashtag-heading">
              <div>
                <span>대표 카테고리</span>
                <strong>
                  {result.summary
                    .representative_category ||
                    "카테고리 없음"}
                </strong>
              </div>

              <div>
                <span>대표 해시태그</span>
                <strong>
                  상위{" "}
                  {Math.min(
                    10,
                    result.keywords.length,
                  )}
                  개
                </strong>
              </div>
            </div>

            <div className="keyword-hashtag-list">
              {result.keywords
                .slice(0, 10)
                .map((item, index) => (
                  <span
                    key={`representative-hashtag-${item.keyword}`}
                    className="keyword-representative-hashtag"
                  >
                    <small>{index + 1}</small>

                    <span className="keyword-hashtag-copy">
                      <strong>
                        #
                        {item.keyword.replace(
                          /\s+/g,
                          "",
                        )}
                      </strong>

                      <em>
                        총 검색량{" "}
                        {item.total_volume.toLocaleString()}
                      </em>
                    </span>
                  </span>
                ))}
            </div>
          </section>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: "10px",
              marginBottom: "10px",
            }}
          >
            <div
              className="result-summary"
              style={{ marginBottom: 0 }}
            >
              연관 키워드{" "}
              {result.count.toLocaleString()}개 ·
              카테고리와 해시태그를 포함한 통합 결과
            </div>

            <button
              type="button"
              className="secondary-button"
              onClick={() =>
                void handleExcelDownload()
              }
              disabled={excelPending}
            >
              {excelPending
                ? "엑셀 생성 중..."
                : "📥 엑셀 다운로드"}
            </button>
          </div>

          <div className="table-scroll">
            <table className="result-table keyword-unified-table">
              <thead>
                <tr>
                  <th>키워드</th>
                  <th>PC 검색량</th>
                  <th>모바일 검색량</th>
                  <th>총 검색량</th>
                  <th>PC 평균 클릭</th>
                  <th>모바일 평균 클릭</th>
                  <th>쇼핑 상품 수</th>
                  <th>경쟁도</th>
                  <th>대표 카테고리·해시태그</th>
                </tr>
              </thead>

              <tbody>
                {result.keywords.map((item) => (
                  <tr key={item.keyword}>
                    <td>
                      <strong>{item.keyword}</strong>
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
                      <strong>
                        {item.total_volume.toLocaleString()}
                      </strong>
                    </td>

                    <td>
                      {item.average_pc_clicks.toLocaleString(
                        undefined,
                        {
                          maximumFractionDigits: 1,
                        },
                      )}
                    </td>

                    <td>
                      {item.average_mobile_clicks.toLocaleString(
                        undefined,
                        {
                          maximumFractionDigits: 1,
                        },
                      )}
                    </td>

                    <td>
                      {item.product_count.toLocaleString()}
                    </td>

                    <td>
                      {item.competition || "-"}
                    </td>

                    <td>
                      <div className="keyword-category-cell">
                        <strong>
                          {item.representative_category ||
                            "카테고리 없음"}
                        </strong>

                        <span className="keyword-hashtag">
                          #
                          {item.keyword.replace(
                            /\s+/g,
                            "",
                          )}
                        </span>

                        {item.category_sample_count > 0 && (
                          <small>
                            카테고리 표본{" "}
                            {item.category_sample_count.toLocaleString()}
                            개
                          </small>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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


      {/* candidate-analysis-excel-export */}
      {result && (
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            marginBottom: "16px",
          }}
        >
          <button
            type="button"
            className="secondary-button"
            onClick={async () => {
              try {
                const blob =
                  await exportCandidateAnalysisExcel(
                    result,
                  );

                const keywordText =
                  result.keywords
                    .slice(0, 5)
                    .join("-") || "분석결과";

                downloadExcelBlob(
                  blob,
                  `사입후보_${keywordText}`,
                );
              } catch (error) {
                window.alert(
                  getDownloadErrorMessage(error),
                );
              }
            }}
          >
            📥 사입후보 엑셀 다운로드
          </button>
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
              <div className="candidate-subtext">
                보유상품 제외{" "}
                {result.summary.excluded_owned_count
                  .toLocaleString()}건
              </div>
              <div className="candidate-subtext">
                유사상품 제외{" "}
                {result.summary.excluded_similar_count
                  .toLocaleString()}건
              </div>
              <div className="candidate-subtext">
                보유 검토{" "}
                {result.summary.ownership_review_count
                  .toLocaleString()}건
              </div>
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
                    <th>점수·등급</th>
                    <th>상품명·추천 근거</th>
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
                        <div className="candidate-subtext">
                          {item.recommendation_grade}
                        </div>
                        <div className="candidate-subtext">
                          수요 {item.score_detail.demand}
                          {" · "}노출 {item.score_detail.exposure}
                        </div>
                        <div className="candidate-subtext">
                          관련성 {item.score_detail.relevance}
                          {" · "}카테고리 {item.score_detail.category}
                        </div>
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

                        {item.ownership_review && (
                          <div className="candidate-subtext">
                            ⚠️ 보유 가능성{" "}
                            {item.ownership_confidence}%
                            {item.matched_owned_product && (
                              <>
                                {" · "}비교:{" "}
                                {item.matched_owned_product}
                              </>
                            )}
                          </div>
                        )}

                        {item.recommendation_reasons.map(
                          (reason) => (
                            <div
                              className="candidate-subtext"
                              key={reason}
                            >
                              ✅ {reason}
                            </div>
                          ),
                        )}

                        {item.warnings.map((warning) => (
                          <div
                            className="candidate-subtext"
                            key={warning}
                          >
                            ⚠️ {warning}
                          </div>
                        ))}
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
                        <div className="candidate-subtext">
                          관측 판매처{" "}
                          {item.observed_seller_count
                            .toLocaleString()}곳
                        </div>
                        <div className="candidate-subtext">
                          가격 안정성{" "}
                          {item.score_detail.price_stability}점
                        </div>
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


      {/* cross-purchase-excel-export */}
      {result && (
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            marginBottom: "16px",
          }}
        >
          <button
            type="button"
            className="secondary-button"
            onClick={async () => {
              try {
                const blob =
                  await exportCrossPurchaseAnalysisExcel(
                    result,
                  );

                downloadExcelBlob(
                  blob,
                  `교차구매_${
                    result.target_query ||
                    "분석결과"
                  }`,
                );
              } catch (error) {
                window.alert(
                  getDownloadErrorMessage(error),
                );
              }
            }}
          >
            📥 교차구매 결과 엑셀 다운로드
          </button>
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
                    <th>추천</th>
                    <th>상품번호</th>
                    <th>함께 산 상품</th>
                    <th>함께 구매</th>
                    <th>Confidence</th>
                    <th>Support</th>
                    <th>Lift</th>
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
                      <td>
                        <strong className="candidate-score">
                          {item.recommendation_score}
                        </strong>
                        <div className="candidate-subtext">
                          {item.recommendation_grade}
                        </div>
                      </td>
                      <td>{item.product_id || "-"}</td>
                      <td>
                        <strong>
                          {item.product_name}
                        </strong>

                        {item.warnings.map((warning) => (
                          <div
                            className="candidate-subtext"
                            key={warning}
                          >
                            ⚠️ {warning}
                          </div>
                        ))}
                      </td>
                      <td>
                        {item.together_order_count
                          .toLocaleString()}건
                        <div className="candidate-subtext">
                          수량{" "}
                          {item.together_quantity
                            .toLocaleString()}개
                        </div>
                        {item.together_revenue > 0 && (
                          <div className="candidate-subtext">
                            매출{" "}
                            {item.together_revenue
                              .toLocaleString()}원
                          </div>
                        )}
                      </td>
                      <td>
                        <strong className="cross-rate">
                          {item.confidence}%
                        </strong>
                      </td>
                      <td>{item.support}%</td>
                      <td>
                        <strong>
                          {item.lift.toFixed(2)}
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
  const [diagnosisMode, setDiagnosisMode] =
    useState<"selected" | "all">("selected");
  const [diagnosisDays, setDiagnosisDays] =
    useState<7 | 14 | 30>(7);
  const [
    excludeOffCampaigns,
    setExcludeOffCampaigns,
  ] = useState(true);
  const [diagnosisPending, setDiagnosisPending] =
    useState(false);
  const [diagnosisError, setDiagnosisError] =
    useState("");
  const [
    diagnosisResult,
    setDiagnosisResult,
  ] =
    useState<AdvertisingDiagnosisResponse | null>(
      null,
    );

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

  async function handleAdvertisingDiagnosis() {
    if (
      diagnosisMode === "selected" &&
      selectedAdgroupIds.length === 0
    ) {
      setDiagnosisError(
        "진단할 광고그룹을 한 개 이상 선택해 주세요.",
      );
      setActiveTab("adgroups");
      return;
    }

    const selectedGroups =
      result?.adgroups.filter((adgroup) =>
        selectedAdgroupIds.includes(
          adgroup.adgroup_id,
        ),
      ) ?? [];

    const targetMap = new Map<string, string[]>();

    for (const adgroup of selectedGroups) {
      const ids =
        targetMap.get(adgroup.campaign_id) ?? [];
      ids.push(adgroup.adgroup_id);
      targetMap.set(adgroup.campaign_id, ids);
    }

    const targets = Array.from(
      targetMap.entries(),
    ).map(([campaignId, adgroupIds]) => ({
      campaign_id: campaignId,
      adgroup_ids: adgroupIds,
    }));

    setDiagnosisPending(true);
    setDiagnosisError("");

    try {
      const response = await diagnoseAdvertising({
        mode: diagnosisMode,
        targets:
          diagnosisMode === "selected"
            ? targets
            : [],
        days: diagnosisDays,
        exclude_off_campaigns:
          excludeOffCampaigns,
      });

      setDiagnosisResult(response);
    } catch (requestError) {
      setDiagnosisResult(null);
      setDiagnosisError(
        requestError instanceof ApiError
          ? requestError.message
          : "광고 진단 서버에 연결하지 못했습니다.",
      );
    } finally {
      setDiagnosisPending(false);
    }
  }

  function downloadDiagnosisCsv() {
    if (!diagnosisResult) {
      return;
    }

    const headers = [
      "상태",
      "우선순위",
      "캠페인",
      "광고그룹",
      "상품명",
      "ON/OFF",
      "입찰가",
      "품질지수",
      "노출",
      "클릭",
      "CTR",
      "평균순위",
      "비용",
      "전환",
      "진단",
      "개선 조언",
    ];

    const values = diagnosisResult.rows.map(
      (row) => [
        row.status_icon,
        row.priority,
        row.campaign_name,
        row.adgroup_name,
        row.product_name,
        row.active ? "ON" : "OFF",
        row.bid_amount,
        row.quality_grade,
        row.impressions,
        row.clicks,
        row.ctr,
        row.average_rank,
        row.cost,
        row.conversions,
        row.verdict,
        row.advice,
      ],
    );

    const escapeCsv = (value: unknown) =>
      `"${String(value ?? "").replace(
        /"/g,
        '""',
      )}"`;

    const csv = [headers, ...values]
      .map((row) =>
        row.map(escapeCsv).join(","),
      )
      .join("\n");

    const blob = new Blob(
      ["\uFEFF", csv],
      {
        type: "text/csv;charset=utf-8",
      },
    );
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    const timestamp =
      diagnosisResult.collected_at
        .replace(/[^0-9]/g, "")
        .slice(0, 14);

    anchor.href = url;
    anchor.download =
      `광고진단_${timestamp || "result"}.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

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
            activeTab === "adgroups"
              ? "block"
              : "none",
          marginTop: "20px",
        }}
      >
        <section
          className="search-panel"
          style={{
            display: "grid",
            gap: "16px",
          }}
        >
          <div>
            <p className="eyebrow">
              NAVER AD DIAGNOSIS
            </p>
            <h3 style={{ margin: "0 0 8px" }}>
              실제 광고 성과 진단
            </h3>
            <p
              style={{
                margin: 0,
                color: "#667085",
                lineHeight: 1.6,
              }}
            >
              선택한 광고그룹 또는 전체 쇼핑 광고의
              노출·클릭·순위·품질·비용을 분석합니다.
            </p>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit, minmax(180px, 1fr))",
              gap: "12px",
            }}
          >
            <div className="field-group">
              <label htmlFor="diagnosis-mode">
                진단 범위
              </label>
              <select
                id="diagnosis-mode"
                value={diagnosisMode}
                onChange={(event) =>
                  setDiagnosisMode(
                    event.target.value as
                      | "selected"
                      | "all",
                  )
                }
                disabled={diagnosisPending}
              >
                <option value="selected">
                  선택한 광고그룹
                </option>
                <option value="all">
                  전체 쇼핑 광고
                </option>
              </select>
            </div>

            <div className="field-group">
              <label htmlFor="diagnosis-days">
                진단 기간
              </label>
              <select
                id="diagnosis-days"
                value={diagnosisDays}
                onChange={(event) =>
                  setDiagnosisDays(
                    Number(event.target.value) as
                      | 7
                      | 14
                      | 30,
                  )
                }
                disabled={diagnosisPending}
              >
                <option value={7}>최근 7일</option>
                <option value={14}>최근 14일</option>
                <option value={30}>최근 30일</option>
              </select>
            </div>

            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: "9px",
                minHeight: "48px",
                alignSelf: "end",
                fontWeight: 700,
              }}
            >
              <input
                type="checkbox"
                checked={excludeOffCampaigns}
                onChange={(event) =>
                  setExcludeOffCampaigns(
                    event.target.checked,
                  )
                }
                disabled={diagnosisPending}
              />
              중지 캠페인 제외
            </label>
          </div>

          {diagnosisMode === "selected" && (
            <div className="info-message">
              현재 선택된 광고그룹{" "}
              <strong>
                {selectedAdgroupIds.length}개
              </strong>
              를 진단합니다.
            </div>
          )}

          {diagnosisMode === "all" && (
            <div className="info-message">
              전체 쇼핑 광고를 대상으로 진단합니다.
              광고 수에 따라 시간이 다소 걸릴 수 있습니다.
            </div>
          )}

          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "10px",
            }}
          >
            <button
              type="button"
              className="primary-button"
              onClick={() =>
                void handleAdvertisingDiagnosis()
              }
              disabled={
                diagnosisPending ||
                (diagnosisMode === "selected" &&
                  selectedAdgroupIds.length === 0)
              }
            >
              {diagnosisPending
                ? "광고 진단 중..."
                : "🔎 광고 진단 실행"}
            </button>

            {diagnosisResult && (
              <>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={downloadDiagnosisCsv}
                  disabled={diagnosisPending}
                >
                  CSV 다운로드
                </button>

                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => {
                    setDiagnosisResult(null);
                    setDiagnosisError("");
                  }}
                  disabled={diagnosisPending}
                >
                  결과 지우기
                </button>
              </>
            )}
          </div>
        </section>

        {diagnosisError && (
          <div className="error-message">
            {diagnosisError}
          </div>
        )}

        {diagnosisPending && (
          <div className="empty-state compact-state">
            <span>⏳</span>
            <h3>광고 성과를 진단하고 있습니다.</h3>
            <p>
              광고와 통계 조회 후 결과를 저장하는 중입니다.
              창을 닫지 말고 기다려 주세요.
            </p>
          </div>
        )}

        {diagnosisResult && !diagnosisPending && (
          <section
            className="rank-results"
            style={{
              display: "grid",
              gap: "18px",
            }}
          >
            <div className="result-summary">
              진단 시각:{" "}
              {diagnosisResult.collected_at} · 최근{" "}
              {diagnosisResult.days}일 · 소요{" "}
              {diagnosisResult.elapsed_seconds.toLocaleString()}
              초
            </div>

            <div className="metric-grid">
              <article className="metric-card">
                <span>진단 광고</span>
                <strong>
                  {diagnosisResult.total_ads.toLocaleString()}
                  개
                </strong>
              </article>

              <article className="metric-card">
                <span>총 노출</span>
                <strong>
                  {diagnosisResult.total_impressions.toLocaleString()}
                </strong>
              </article>

              <article className="metric-card">
                <span>총 클릭</span>
                <strong>
                  {diagnosisResult.total_clicks.toLocaleString()}
                </strong>
              </article>

              <article className="metric-card">
                <span>총 비용</span>
                <strong>
                  {diagnosisResult.total_cost.toLocaleString()}
                  원
                </strong>
              </article>

              <article className="metric-card">
                <span>긴급 점검</span>
                <strong>
                  {diagnosisResult.urgent_count.toLocaleString()}
                  개
                </strong>
              </article>

              <article className="metric-card">
                <span>저장 결과</span>
                <strong>
                  {diagnosisResult.saved_count.toLocaleString()}
                  건
                </strong>
              </article>
            </div>

            {diagnosisResult.save_message && (
              <div className="info-message">
                {diagnosisResult.save_message}
              </div>
            )}

            {diagnosisResult.errors.length > 0 && (
              <div className="error-message">
                <strong>
                  일부 광고 조회 오류{" "}
                  {diagnosisResult.errors.length}건
                </strong>
                <ul
                  style={{
                    marginBottom: 0,
                    paddingLeft: "20px",
                  }}
                >
                  {diagnosisResult.errors.map(
                    (message, index) => (
                      <li key={`${message}-${index}`}>
                        {message}
                      </li>
                    ),
                  )}
                </ul>
              </div>
            )}

            <div>
              <h3>우선 점검 광고 TOP 5</h3>

              {diagnosisResult.rows.length === 0 ? (
                <div className="empty-state compact-state">
                  <span>📭</span>
                  <h3>진단 결과가 없습니다.</h3>
                </div>
              ) : (
                <div className="table-scroll">
                  <table className="result-table">
                    <thead>
                      <tr>
                        <th>상태</th>
                        <th>상품명</th>
                        <th>캠페인</th>
                        <th>광고그룹</th>
                        <th>진단</th>
                        <th>개선 조언</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...diagnosisResult.rows]
                        .sort(
                          (left, right) =>
                            right.priority -
                            left.priority,
                        )
                        .slice(0, 5)
                        .map((row) => (
                          <tr key={`top-${row.ad_id}`}>
                            <td>{row.status_icon}</td>
                            <td>
                              <strong>
                                {row.product_name || "-"}
                              </strong>
                            </td>
                            <td>
                              {row.campaign_name || "-"}
                            </td>
                            <td>
                              {row.adgroup_name || "-"}
                            </td>
                            <td>{row.verdict || "-"}</td>
                            <td>{row.advice || "-"}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div>
              <h3>
                이전 진단 대비 악화 항목 (
                {diagnosisResult.changes.length})
              </h3>

              {diagnosisResult.previous_collected_at && (
                <p className="result-summary">
                  비교 기준:{" "}
                  {diagnosisResult.previous_collected_at}
                </p>
              )}

              {diagnosisResult.changes.length === 0 ? (
                <div className="info-message">
                  이전 진단 대비 악화된 항목이 없습니다.
                </div>
              ) : (
                <div className="table-scroll">
                  <table className="result-table">
                    <thead>
                      <tr>
                        <th>상품명</th>
                        <th>캠페인</th>
                        <th>변화</th>
                        <th>심각도</th>
                      </tr>
                    </thead>
                    <tbody>
                      {diagnosisResult.changes.map(
                        (change, index) => (
                          <tr
                            key={`${change.ad_id}-${index}`}
                          >
                            <td>
                              <strong>
                                {change.product_name || "-"}
                              </strong>
                            </td>
                            <td>
                              {change.campaign_name || "-"}
                            </td>
                            <td>{change.change}</td>
                            <td>{change.severity}</td>
                          </tr>
                        ),
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div>
              <h3>
                전체 광고 성과 (
                {diagnosisResult.rows.length})
              </h3>

              <div className="table-scroll">
                <table className="result-table">
                  <thead>
                    <tr>
                      <th>상태</th>
                      <th>캠페인</th>
                      <th>광고그룹</th>
                      <th>상품명</th>
                      <th>ON/OFF</th>
                      <th>입찰가</th>
                      <th>품질</th>
                      <th>노출</th>
                      <th>클릭</th>
                      <th>CTR</th>
                      <th>평균순위</th>
                      <th>비용</th>
                      <th>전환</th>
                      <th>진단</th>
                      <th>개선 조언</th>
                    </tr>
                  </thead>

                  <tbody>
                    {diagnosisResult.rows.map(
                      (row) => (
                        <tr key={row.ad_id}>
                          <td>{row.status_icon}</td>
                          <td>
                            {row.campaign_name || "-"}
                          </td>
                          <td>
                            {row.adgroup_name || "-"}
                          </td>
                          <td>
                            <strong>
                              {row.product_name || "-"}
                            </strong>
                          </td>
                          <td>
                            {row.active ? "ON" : "OFF"}
                          </td>
                          <td>
                            {row.bid_amount.toLocaleString()}
                            원
                          </td>
                          <td>
                            {row.quality_grade || "-"}
                          </td>
                          <td>
                            {row.impressions.toLocaleString()}
                          </td>
                          <td>
                            {row.clicks.toLocaleString()}
                          </td>
                          <td>
                            {row.ctr.toFixed(2)}%
                          </td>
                          <td>
                            {row.average_rank > 0
                              ? row.average_rank.toFixed(1)
                              : "-"}
                          </td>
                          <td>
                            {row.cost.toLocaleString()}원
                          </td>
                          <td>
                            {row.conversions.toLocaleString()}
                          </td>
                          <td>{row.verdict || "-"}</td>
                          <td>{row.advice || "-"}</td>
                        </tr>
                      ),
                    )}
                  </tbody>
                </table>
              </div>
            </div>
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
