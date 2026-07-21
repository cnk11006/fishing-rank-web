"use client";

import Image from "next/image";
import { FormEvent, useState } from "react";

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
  const [dashboardPreview, setDashboardPreview] = useState(false);
  const [activeNavigation, setActiveNavigation] =
    useState<NavigationId>("rank");
  const [loginMessage, setLoginMessage] = useState("");

  const sheetUrl =
    process.env.NEXT_PUBLIC_GOOGLE_SHEET_URL ?? "";

  const activeItem =
    navigationItems.find((item) => item.id === activeNavigation) ??
    navigationItems[0];

  function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoginMessage(
      "로그인 API는 다음 백엔드 작업에서 연결됩니다.",
    );
  }

  if (!dashboardPreview) {
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
              required
            />

            <button className="primary-button" type="submit">
              로그인
            </button>
          </form>

          {loginMessage && (
            <div className="info-message">{loginMessage}</div>
          )}

          <button
            type="button"
            className="preview-button"
            onClick={() => setDashboardPreview(true)}
          >
            개발 중인 대시보드 화면 미리보기
          </button>

          <p className="preview-warning">
            현재는 화면 확인 단계입니다. 실제 인증은 Python 백엔드
            연결 후 활성화됩니다.
          </p>
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
            onClick={() => setDashboardPreview(false)}
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
  return (
    <>
      <form
        className="search-panel"
        onSubmit={(event) => event.preventDefault()}
      >
        <div className="field-group">
          <label htmlFor="rank-keyword">검색 키워드</label>
          <input
            id="rank-keyword"
            type="text"
            placeholder="예: 낚시의자"
          />
        </div>

        <div className="field-group">
          <label htmlFor="rank-limit">조회 범위</label>
          <select id="rank-limit" defaultValue="400">
            <option value="100">100위까지</option>
            <option value="200">200위까지</option>
            <option value="300">300위까지</option>
            <option value="400">400위까지</option>
          </select>
        </div>

        <button className="primary-button search-button" type="submit">
          🔍 순위 검색
        </button>
      </form>

      <div className="metric-grid">
        <article className="metric-card">
          <span>검색 키워드</span>
          <strong>-</strong>
        </article>
        <article className="metric-card">
          <span>피싱템 노출 상품</span>
          <strong>0</strong>
        </article>
        <article className="metric-card">
          <span>최고 순위</span>
          <strong>-</strong>
        </article>
        <article className="metric-card">
          <span>조회 범위</span>
          <strong>400위</strong>
        </article>
      </div>

      <div className="empty-state">
        <span>🔎</span>
        <h3>검색 결과가 여기에 표시됩니다.</h3>
        <p>
          실제 순위 검색은 Python 백엔드 API 연결 후 활성화됩니다.
        </p>
      </div>
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
