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
  highest_price: number;
  link: string;
  image: string;
  product_type: number;
  product_id: string;
  brand: string;
  maker: string;
  categories: string[];
  is_ours: boolean;
  is_catalog: boolean;
  catalog_badge: string;
};

export type RankSearchResponse = {
  keyword: string;
  limit: number;
  include_special_products: boolean;
  searched_at: string;
  total_results: number;
  fetched_count: number;
  match_count: number;
  best_rank: number | null;
  top10_price_summary: {
    count: number;
    lowest: number;
    average: number;
    highest: number;
    our_average: number;
    difference_percent: number | null;
  };
  market_top10: RankSearchItem[];
  warnings: string[];
  partial_success: boolean;
  elapsed_seconds: number;
  results: RankSearchItem[];
  save_scheduled: false;
};

export type SaveSelectedRankResponse = {
  message: string;
  saved_count: number;
  selected_count: number;
  monitor_added_count: number;
  monitor_duplicate_count: number;
  monitor_errors: string[];
  saved_items: RankSearchItem[];
};

export function searchRank(
  keyword: string,
  limit: number,
  includeSpecialProducts: boolean,
) {
  return apiRequest<RankSearchResponse>(
    "/api/rank/search",
    {
      method: "POST",
      body: JSON.stringify({
        keyword,
        limit,
        include_special_products:
          includeSpecialProducts,
      }),
    },
  );
}

export function saveSelectedRankItems(
  keyword: string,
  items: RankSearchItem[],
) {
  return apiRequest<SaveSelectedRankResponse>(
    "/api/rank/save-selected",
    {
      method: "POST",
      body: JSON.stringify({
        keyword,
        items,
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

export function updateMonitoringItem(input: {
  item_id: string;
  keyword: string;
  memo: string;
  product_id: string;
  product_name: string;
}) {
  return apiRequest<{
    message: string;
    item: MonitorItem;
  }>("/api/monitoring/update", {
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

export function collectSelectedMonitoringRanks(
  itemIds: string[],
) {
  return apiRequest<MonitoringCollectResponse>(
    "/api/monitoring/collect-selected",
    {
      method: "POST",
      body: JSON.stringify({
        item_ids: itemIds,
      }),
    },
  );
}

export type MonitoringHistoryItem = MonitorItem & {
  latest_rank: number | null;
  previous_rank: number | null;
  rank_change: number | null;
  latest_collected_at: string | null;
  previous_collected_at: string | null;
  latest_title: string;
  latest_mall_name: string;
  latest_price: number;
  latest_link: string;
  latest_image: string;
  recent_history: {
    collected_at: string;
    rank: number | null;
  }[];
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
  relatedLimit: 10 | 20 | 30 | 50 | 100,
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


export async function exportKeywordAnalysisExcel(
  keyword: string,
  rows: KeywordAnalysisItem[],
) {
  const response = await fetch(
    "/api/keywords/export",
    {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        keyword,
        rows,
      }),
    },
  );

  if (!response.ok) {
    let data: ApiPayload = {};

    try {
      data = await response.json();
    } catch {
      data = {};
    }

    throw new ApiError(response.status, data);
  }

  return response.blob();
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


export type AdvertisingDiagnosisTarget = {
  campaign_id: string;
  adgroup_ids: string[];
};

export type AdvertisingDiagnosisRow = {
  ad_id: string;
  status_icon: string;
  priority: number;
  campaign_name: string;
  adgroup_name: string;
  product_name: string;
  active: boolean;
  bid_amount: number;
  quality_grade: number;
  impressions: number;
  clicks: number;
  ctr: number;
  average_rank: number;
  cost: number;
  conversions: number;
  verdict: string;
  advice: string;
};

export type AdvertisingDiagnosisChange = {
  ad_id: string;
  product_name: string;
  campaign_name: string;
  change: string;
  severity: number;
};

export type AdvertisingDiagnosisResponse = {
  collected_at: string;
  previous_collected_at: string | null;
  days: number;
  total_ads: number;
  total_impressions: number;
  total_clicks: number;
  total_cost: number;
  urgent_count: number;
  saved_count: number;
  save_message: string;
  errors: string[];
  changes: AdvertisingDiagnosisChange[];
  rows: AdvertisingDiagnosisRow[];
  elapsed_seconds: number;
};

export function diagnoseAdvertising(input: {
  mode: "selected" | "all";
  targets: AdvertisingDiagnosisTarget[];
  days: 7 | 14 | 30;
  exclude_off_campaigns: boolean;
}) {
  return apiRequest<AdvertisingDiagnosisResponse>(
    "/api/advertising/diagnose",
    {
      method: "POST",
      body: JSON.stringify(input),
    },
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


export type CrossPurchaseResultItem = {
  product_id: string;
  product_name: string;
  together_order_count: number;
  cross_purchase_rate: number;
  is_ours: boolean;
  support: number;
  confidence: number;
  lift: number;
  overall_order_count: number;
  together_quantity: number;
  together_revenue: number;
  recommendation_score: number;
  recommendation_grade:
    | "매우 높음"
    | "높음"
    | "보통"
    | "낮음";
  warnings: string[];
};

export type CrossPurchaseResponse = {
  target_query: string;
  summary: {
    uploaded_file_count: number;
    successful_file_count: number;
    file_error_count: number;
    order_row_count: number;
    total_order_count: number;
    target_order_count: number;
    result_count: number;
    duplicate_row_count: number;
    excluded_status_count: number;
    top_n: number;
    min_orders: number;
  };
  results: CrossPurchaseResultItem[];
  file_errors: {
    file_name: string;
    message: string;
  }[];
  analysis_guide: {
    support: string;
    confidence: string;
    lift: string;
  };
  elapsed_seconds: number;
};

export async function analyzeCrossPurchase(
  files: File[],
  targetQuery: string,
  topN: number,
  minOrders: number,
) {
  const formData = new FormData();

  for (const file of files) {
    formData.append("files", file);
  }

  formData.append("target_query", targetQuery);
  formData.append("top_n", String(topN));
  formData.append("min_orders", String(minOrders));

  const response = await fetch(
    "/api/cross-purchase/analyze",
    {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      body: formData,
    },
  );

  let data: ApiPayload = {};

  try {
    data = await response.json();
  } catch {
    data = {};
  }

  if (!response.ok) {
    throw new ApiError(response.status, data);
  }

  return data as CrossPurchaseResponse;
}


export type CandidateResultItem = {
  product_id: string;
  product_name: string;
  brand: string;
  maker: string;
  representative_seller: string;
  best_rank: number;
  representative_price: number;
  category: string;
  link: string;
  image: string;
  search_volume: number;
  volume_keyword: string;
  same_product_owned: boolean;
  product_group_owned: boolean;
  ownership_confidence: number;
  ownership_review: boolean;
  matched_owned_product: string;
  ownership_match_reason: string;
  keywords: string[];
  observed_seller_count: number;
  lowest_price: number;
  highest_price: number;
  average_price: number;
  potential_score: number;
  recommendation_grade:
    | "매우 높음"
    | "높음"
    | "보통"
    | "검토 필요";
  score_detail: {
    demand: number;
    exposure: number;
    relevance: number;
    category: number;
    seller_diversity: number;
    price_stability: number;
  };
  recommendation_reasons: string[];
  warnings: string[];
};

export type CandidateAnalysisResponse = {
  summary: {
    keyword_count: number;
    master_product_count: number;
    candidate_count: number;
    error_count: number;
    excluded_our_store_count: number;
    excluded_owned_count: number;
    excluded_product_id_count: number;
    excluded_exact_name_count: number;
    excluded_similar_count: number;
    ownership_review_count: number;
    max_results: number;
    result_limit: number;
    min_volume: number;
  };
  keywords: string[];
  results: CandidateResultItem[];
  errors: {
    keyword: string;
    message: string;
  }[];
  elapsed_seconds: number;
};

export type CandidateAnalysisOptions = {
  maxResults: 100 | 200 | 300 | 400;
  resultLimit: number;
  minVolume: number;
  excludeOwned: boolean;
  excludeGroup: boolean;
  excludeUsed: boolean;
  excludeRental: boolean;
  excludeOverseas: boolean;
};

export async function analyzeCandidates(
  masterFile: File,
  keywords: string,
  options: CandidateAnalysisOptions,
) {
  const formData = new FormData();

  formData.append("master_file", masterFile);
  formData.append("keywords", keywords);
  formData.append(
    "max_results",
    String(options.maxResults),
  );
  formData.append(
    "result_limit",
    String(options.resultLimit),
  );
  formData.append(
    "min_volume",
    String(options.minVolume),
  );
  formData.append(
    "exclude_owned",
    String(options.excludeOwned),
  );
  formData.append(
    "exclude_group",
    String(options.excludeGroup),
  );
  formData.append(
    "exclude_used",
    String(options.excludeUsed),
  );
  formData.append(
    "exclude_rental",
    String(options.excludeRental),
  );
  formData.append(
    "exclude_overseas",
    String(options.excludeOverseas),
  );

  const response = await fetch(
    "/api/candidates/analyze",
    {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      body: formData,
    },
  );

  let data: ApiPayload = {};

  try {
    data = await response.json();
  } catch {
    data = {};
  }

  if (!response.ok) {
    throw new ApiError(response.status, data);
  }

  return data as CandidateAnalysisResponse;
}

export type DataManagementOverview = {
  summary: {
    worksheet_count: number;
    rank_record_count: number;
    monitor_count: number;
    legacy_sheet_count: number;
    migrated_legacy_sheet_count: number;
    pending_legacy_sheet_count: number;
    latest_collected_at: string;
  };
  legacy_sheets: string[];
  migrated_legacy_sheets: string[];
  pending_legacy_sheets: string[];
  worksheets: {
    title: string;
    is_system: boolean;
  }[];
  system: {
    naver_shopping_ready: boolean;
    naver_search_ad_ready: boolean;
    google_sheets_ready: boolean;
    authentication_ready: boolean;
    environment: string;
    timezone: string;
  };
};

export type RankMigrationResponse = {
  total_migrated_count: number;
  result_count: number;
  source_sheets_deleted: boolean;
  results: {
    source_sheet: string;
    migrated_count: number;
    status: "completed" | "skipped" | "error";
    message: string;
  }[];
};

export type CacheClearResponse = {
  message: string;
  cleared: {
    keyword_category_cache: number;
    season_analysis_cache: number;
    google_sheets_connection_cache: number;
  };
};

export function getDataManagementOverview() {
  return apiRequest<DataManagementOverview>(
    "/api/data-management/overview",
  );
}

export function migrateLegacyRankSheets() {
  return apiRequest<RankMigrationResponse>(
    "/api/data-management/migrate",
    {
      method: "POST",
      body: JSON.stringify({
        backup_confirmed: true,
      }),
    },
  );
}

export function clearApplicationCaches() {
  return apiRequest<CacheClearResponse>(
    "/api/data-management/clear-cache",
    {
      method: "POST",
    },
  );
}


export type ProductNameMode = "new" | "existing";

export type ProductNameKeywordSuggestion = {
  keyword: string;
  total_volume: number;
  competition: string;
  representative_category: string;
};

export type ProductNameCandidate = {
  style: "간결형" | "균형형" | "확장형";
  title: string;
  score: number;
  score_breakdown: {
    main_keyword: number;
    product_relevance: number;
    search_demand: number;
    competitor_usage: number;
    category_fit: number;
    readability: number;
    policy_compliance: number;
  };
  length: number;
  reason: string;
  used_keywords: string[];
  warnings: string[];
  missing_required_words: string[];
  changes: {
    kept: string[];
    added: string[];
    removed: string[];
  };
};

export type ProductNameRecommendationResponse = {
  mode: ProductNameMode;
  main_keyword: string;
  product_type: string;
  brand: string;
  model_name: string;
  current_title: string;
  product_url: string;
  representative_category: string;
  current_title_warnings: string[];
  current_title_diagnosis: {
    keep: string[];
    remove: string[];
    consider: string[];
  };
  keyword_suggestions: ProductNameKeywordSuggestion[];
  competitor_terms: {
    term: string;
    product_count: number;
    frequency: number;
    recommendation: string;
  }[];
  competitor_titles: {
    rank: number;
    title: string;
    mall_name: string;
  }[];
  candidates: ProductNameCandidate[];
  warnings: string[];
};

export function recommendProductNames(input: {
  mode: ProductNameMode;
  main_keyword: string;
  product_type: string;
  brand: string;
  model_name: string;
  features: string[];
  required_words: string[];
  excluded_words: string[];
  current_title: string;
  product_url: string;
}) {
  return apiRequest<ProductNameRecommendationResponse>(
    "/api/product-names/recommend",
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
}
