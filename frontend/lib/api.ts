type ApiPayload = Record<string, unknown>;

export class ApiError extends Error {
  status: number;
  data: ApiPayload;

  constructor(
    status: number,
    data: ApiPayload,
  ) {
    const detail = data.detail;
    let message = "요청을 처리하지 못했습니다.";

    if (typeof detail === "string") {
      message = detail;
    } else if (
      detail &&
      typeof detail === "object" &&
      "message" in detail &&
      typeof detail.message === "string"
    ) {
      message = detail.message;

      if (
        "retry_after" in detail &&
        typeof detail.retry_after === "number"
      ) {
        message += ` ${detail.retry_after}초 후 다시 시도하세요.`;
      } else if (
        "remaining_attempts" in detail &&
        typeof detail.remaining_attempts === "number"
      ) {
        message += ` 남은 시도 횟수: ${detail.remaining_attempts}회`;
      }
    } else if (
      typeof data.message === "string"
    ) {
      message = data.message;
    }

    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...options,
    credentials: "include",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  let data: ApiPayload = {};

  try {
    data = await response.json();
  } catch {
    data = {};
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      data,
    );
  }

  return data as T;
}

export function getAuthenticationStatus() {
  return apiRequest<{
    authenticated: boolean;
  }>("/api/auth/status");
}

export function loginWithPassword(
  password: string,
) {
  return apiRequest<{
    authenticated: boolean;
    message: string;
  }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}

export function logoutSession() {
  return apiRequest<{
    authenticated: boolean;
    message: string;
  }>("/api/auth/logout", {
    method: "POST",
  });
}

export type RankSearchItem = {
  rank: number;
  title: string;
  mall_name: string;
  price: number;
  link: string;
  image: string;
  product_type: number;
  product_id: string;
  brand: string;
  maker: string;
  categories: string[];
};

export type RankSearchResponse = {
  keyword: string;
  limit: number;
  total_results: number;
  fetched_count: number;
  match_count: number;
  best_rank: number | null;
  elapsed_seconds: number;
  results: RankSearchItem[];
};

export function searchRank(
  keyword: string,
  limit: number,
) {
  return apiRequest<RankSearchResponse>(
    "/api/rank/search",
    {
      method: "POST",
      body: JSON.stringify({
        keyword,
        limit,
      }),
    },
  );
}

export type MonitorItem = {
  item_id: string;
  keyword: string;
  registered_at: string;
  memo: string;
  product_id: string;
  product_name: string;
  row_number?: number;
};

export function getMonitoringList() {
  return apiRequest<{
    count: number;
    items: MonitorItem[];
  }>("/api/monitoring/list");
}

export function addMonitoringItem(input: {
  keyword: string;
  memo: string;
  product_id: string;
  product_name: string;
}) {
  return apiRequest<{
    message: string;
    item: MonitorItem;
  }>("/api/monitoring/add", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function deleteMonitoringItems(
  itemIds: string[],
) {
  return apiRequest<{
    message: string;
    deleted_count: number;
  }>("/api/monitoring/delete", {
    method: "POST",
    body: JSON.stringify({
      item_ids: itemIds,
    }),
  });
}

export type MonitoringCollectItem = MonitorItem & {
  status: "exposed" | "not_exposed" | "error";
  rank: number | null;
  matched_count: number;
  message: string;
};

export type MonitoringCollectResponse = {
  total_items: number;
  unique_keywords: number;
  exposed_count: number;
  not_exposed_count: number;
  error_count: number;
  saved_records: number;
  elapsed_seconds: number;
  results: MonitoringCollectItem[];
};

export function collectMonitoringRanks() {
  return apiRequest<MonitoringCollectResponse>(
    "/api/monitoring/collect",
    {
      method: "POST",
    },
  );
}

export type MonitoringHistoryItem = MonitorItem & {
  latest_rank: number | null;
  previous_rank: number | null;
  rank_change: number | null;
  latest_collected_at: string | null;
  previous_collected_at: string | null;
  status:
    | "no_history"
    | "not_exposed"
    | "first"
    | "up"
    | "down"
    | "same";
  message: string;
};

export function getMonitoringHistory() {
  return apiRequest<{
    count: number;
    history_row_count: number;
    items: MonitoringHistoryItem[];
  }>("/api/monitoring/history");
}

export type KeywordAnalysisItem = {
  keyword: string;
  pc_volume: number;
  pc_volume_raw: string;
  pc_estimated: boolean;
  mobile_volume: number;
  mobile_volume_raw: string;
  mobile_estimated: boolean;
  total_volume: number;
  competition: string;
  average_pc_clicks: number;
  average_mobile_clicks: number;
  product_count: number;
  representative_category: string;
  category_sample_count: number;
  category_cached: boolean;
};

export type KeywordAnalysisResponse = {
  keyword: string;
  related_limit: number;
  count: number;
  elapsed_seconds: number;
  summary: KeywordAnalysisItem;
  keywords: KeywordAnalysisItem[];
};

export function analyzeKeywords(
  keyword: string,
  relatedLimit: 10 | 20 | 30,
) {
  return apiRequest<KeywordAnalysisResponse>(
    "/api/keywords/analyze",
    {
      method: "POST",
      body: JSON.stringify({
        keyword,
        related_limit: relatedLimit,
      }),
    },
  );
}

export type AdvertisingCampaign = {
  campaign_id: string;
  name: string;
  campaign_type: string;
  daily_budget: number;
  uses_daily_budget: boolean;
  user_locked: boolean;
  status: "active" | "paused";
  registered_at: string;
  edited_at: string;
};

export type AdvertisingAdgroup = {
  adgroup_id: string;
  campaign_id: string;
  campaign_name: string;
  name: string;
  bid_amount: number;
  daily_budget: number;
  uses_daily_budget: boolean;
  user_locked: boolean;
  api_status: string;
  status_reason: string;
  status: "active" | "paused";
};

export type AdvertisingOverviewResponse = {
  summary: {
    campaign_count: number;
    active_campaign_count: number;
    paused_campaign_count: number;
    adgroup_count: number;
    active_adgroup_count: number;
    paused_adgroup_count: number;
    error_count: number;
  };
  campaigns: AdvertisingCampaign[];
  adgroups: AdvertisingAdgroup[];
  errors: {
    campaign_id: string;
    campaign_name: string;
    message: string;
  }[];
  elapsed_seconds: number;
};

export function getAdvertisingOverview() {
  return apiRequest<AdvertisingOverviewResponse>(
    "/api/advertising/overview",
  );
}



export type SeasonMonthlyItem = {
  period: string;
  month: number;
  month_name: string;
  season: string;
  ratio: number;
  is_partial: boolean;
};

export type SeasonAnalysisResponse = {
  keyword: string;
  months: number;
  cached: boolean;
  summary: {
    pc_volume: number;
    mobile_volume: number;
    total_volume: number;
    current_ratio: number;
    current_period: string;
    current_is_partial: boolean;
    latest_complete_ratio: number;
    latest_complete_period: string;
    peak_ratio: number;
    peak_period: string;
    peak_month: number;
    strongest_season: string;
    trend_status: "rising" | "falling" | "stable";
    trend_label: string;
    trend_change: number;
    preparation_month: number;
    recommendation: string;
  };
  season_scores: {
    season: string;
    average_ratio: number;
    sample_count: number;
  }[];
  monthly: SeasonMonthlyItem[];
  elapsed_seconds: number;
};

export function analyzeSeason(
  keyword: string,
  months: 12 | 24 | 36,
) {
  return apiRequest<SeasonAnalysisResponse>(
    "/api/advertising/season",
    {
      method: "POST",
      body: JSON.stringify({
        keyword,
        months,
      }),
    },
  );
}
