"use client";

import Image from "next/image";
import { FormEvent, useEffect, useState } from "react";
import {
  ApiError,
  getAuthenticationStatus,
  loginWithPassword,
  logoutSession,
  searchRank,
  getMonitoringList,
  addMonitoringItem,
  deleteMonitoringItems,
} from "@/lib/api";
import type {
  RankSearchResponse,
  MonitorItem,
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
            onClick={() => setActiveNavigation(item.id)}
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

        {activeNavigation === "rank" ? (
          <RankSearchPreview />
        ) : activeNavigation === "monitoring" ? (
          <MonitoringManager />
        ) : (
          <FeaturePreview
            icon={activeItem.icon}
            name={activeItem.label}
          />
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
  const [searchPending, setSearchPending] =
    useState(false);
  const [searchError, setSearchError] = useState("");
  const [searchResult, setSearchResult] =
    useState<RankSearchResponse | null>(null);

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

    try {
      const result = await searchRank(
        trimmedKeyword,
        limit,
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

  return (
    <>
      <form
        className="search-panel"
        onSubmit={handleRankSearch}
      >
        <div className="field-group">
          <label htmlFor="rank-keyword">
            검색 키워드
          </label>
          <input
            id="rank-keyword"
            type="text"
            placeholder="예: 낚시의자"
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

        <button
          className="primary-button search-button"
          type="submit"
          disabled={searchPending}
        >
          {searchPending
            ? "검색 중..."
            : "🔍 순위 검색"}
        </button>
      </form>

      {searchError && (
        <div className="error-message">
          {searchError}
        </div>
      )}

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
            {searchResult?.match_count ?? 0}
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
            키워드와 조회 범위를 선택한 후 순위 검색을
            눌러주세요.
          </p>
        </div>
      ) : searchResult.results.length === 0 ? (
        <div className="empty-state">
          <span>📭</span>
          <h3>
            조회 범위 안에 피싱템 상품이 없습니다.
          </h3>
          <p>
            네이버쇼핑 상품 {searchResult.fetched_count}개를
            확인했습니다.
          </p>
        </div>
      ) : (
        <div className="rank-results">
          <div className="result-summary">
            네이버쇼핑 상품{" "}
            {searchResult.fetched_count.toLocaleString()}개 중
            피싱템 상품 {searchResult.match_count}개를
            찾았습니다.
          </div>

          <div className="table-scroll">
            <table className="result-table">
              <thead>
                <tr>
                  <th>순위</th>
                  <th>상품명</th>
                  <th>판매처</th>
                  <th>가격</th>
                  <th>카테고리</th>
                  <th>링크</th>
                </tr>
              </thead>

              <tbody>
                {searchResult.results.map((item) => (
                  <tr
                    key={`${item.product_id}-${item.rank}`}
                  >
                    <td>
                      <strong>{item.rank}위</strong>
                    </td>
                    <td>{item.title}</td>
                    <td>{item.mall_name}</td>
                    <td>
                      {item.price.toLocaleString()}원
                    </td>
                    <td>
                      {item.categories
                        .filter(Boolean)
                        .join(" > ") || "-"}
                    </td>
                    <td>
                      <a
                        href={item.link}
                        target="_blank"
                        rel="noreferrer"
                        className="product-link"
                      >
                        상품 보기
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

function MonitoringManager() {
  const [items, setItems] = useState<MonitorItem[]>([]);
  const [selectedIds, setSelectedIds] =
    useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionPending, setActionPending] =
    useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadItems() {
    setLoading(true);
    setError("");

    try {
      const result = await getMonitoringList();
      setItems(result.items);
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
            className="secondary-button"
            onClick={() => void loadItems()}
            disabled={loading || actionPending}
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
                <th>productId</th>
                <th>메모</th>
                <th>등록일</th>
              </tr>
            </thead>

            <tbody>
              {items.map((item) => (
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
                  <td>{item.product_id || "-"}</td>
                  <td>{item.memo || "-"}</td>
                  <td>{item.registered_at || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
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
