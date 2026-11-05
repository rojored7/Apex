// S5-F2 · US-120, US-121 y US-130 (front): datos de reglas, plantillas e historial (contrato de B6 y B7).
// - useRules(params) y useTemplates(params): GET /notification-rules y /notification-templates con las
//   claves ["notification-rules", "list", params] y ["notification-templates", "list", params]; páginas
//   validadas con Zod. useRuleOptions() y useTemplateOptions() piden hasta 200 para los selectores
//   (claves aparte); las escrituras invalidan todas las de su recurso.
// - useCreateRule, useUpdateRule(id), useCreateTemplate, useUpdateTemplate(id): POST y PATCH por
//   useSensitiveMutation (gcTime 0 y reset al terminar).
// - usePreviewTemplate(): POST /notification-templates/preview {subject, body}; no escribe.
// - useHistory(params): GET /notifications con los filtros; la clave cuelga de ["notifications"], que
//   invalidan abrir WhatsApp y omitir.
import { keepPreviousData, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";
import { api } from "../../core/api/client";
import type { Page } from "../../core/api/page";
import { listParams, MAX_LIMIT } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";
import { useSensitiveMutation } from "../../core/api/useSensitiveMutation";
import {
  previewSchema,
  ruleRowSchema,
  rulesPageSchema,
  templateRowSchema,
  templatesPageSchema,
  type PreviewView,
  type RuleBody,
  type RulePatchBody,
  type RuleRowView,
  type TemplateFormValues,
  type TemplatePatchBody,
  type TemplateRowView,
} from "./adminSchemas";
import { refreshIfStale } from "./api";
import type { HistoryParams } from "./historyFilters";
import { notificationsPageSchema, type NotificationRowView } from "./schemas";

export const RULES_QUERY_KEY = ["notification-rules"] as const;
export const TEMPLATES_QUERY_KEY = ["notification-templates"] as const;

export interface PageParams {
  limit: number;
  offset: number;
}

export const rulesQueryKey = (params: PageParams) => ["notification-rules", "list", params] as const;
export const templatesQueryKey = (params: PageParams) => ["notification-templates", "list", params] as const;
export const historyQueryKey = (params: HistoryParams) => ["notifications", "history", params] as const;

const OPTIONS: PageParams = { limit: MAX_LIMIT, offset: 0 };
const rulePath = (id: string): string => `/notification-rules/${encodeURIComponent(id)}`;
const templatePath = (id: string): string => `/notification-templates/${encodeURIComponent(id)}`;

export function useRules(params: PageParams): UseQueryResult<Page<RuleRowView>> {
  return useQuery({
    queryKey: rulesQueryKey(params),
    queryFn: async ({ signal }) => parseResponse(rulesPageSchema, await api.get<unknown>("/notification-rules", { query: listParams({ ...params }), signal })),
    placeholderData: keepPreviousData,
  });
}

/** Todas las reglas (hasta 200) para el filtro del historial. */
export function useRuleOptions(): UseQueryResult<Page<RuleRowView>> {
  return useQuery({
    queryKey: [...RULES_QUERY_KEY, "options"],
    queryFn: async ({ signal }) => parseResponse(rulesPageSchema, await api.get<unknown>("/notification-rules", { query: listParams({ ...OPTIONS }), signal })),
  });
}

export function useTemplates(params: PageParams): UseQueryResult<Page<TemplateRowView>> {
  return useQuery({
    queryKey: templatesQueryKey(params),
    queryFn: async ({ signal }) => parseResponse(templatesPageSchema, await api.get<unknown>("/notification-templates", { query: listParams({ ...params }), signal })),
    placeholderData: keepPreviousData,
  });
}

/** Todas las plantillas (hasta 200) para el selector de la regla y el nombre en la tabla. */
export function useTemplateOptions(): UseQueryResult<Page<TemplateRowView>> {
  return useQuery({
    queryKey: [...TEMPLATES_QUERY_KEY, "options"],
    queryFn: async ({ signal }) => parseResponse(templatesPageSchema, await api.get<unknown>("/notification-templates", { query: listParams({ ...OPTIONS }), signal })),
  });
}

export function useHistory(params: HistoryParams): UseQueryResult<Page<NotificationRowView>> {
  return useQuery({
    queryKey: historyQueryKey(params),
    queryFn: async ({ signal }) => parseResponse(notificationsPageSchema, await api.get<unknown>("/notifications", { query: listParams({ ...params }), signal })),
    placeholderData: keepPreviousData,
  });
}

export function useCreateRule(): UseMutationResult<RuleRowView, Error, RuleBody> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<RuleRowView, Error, RuleBody>({
    mutationFn: async (body) => parseResponse(ruleRowSchema, await api.post<unknown>("/notification-rules", { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: RULES_QUERY_KEY });
    },
  });
}

export function useUpdateRule(id: string): UseMutationResult<RuleRowView, Error, RulePatchBody> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<RuleRowView, Error, RulePatchBody>({
    mutationFn: async (body) => parseResponse(ruleRowSchema, await api.patch<unknown>(rulePath(id), { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: RULES_QUERY_KEY });
    },
    onError: refreshIfStale(() => {
      void queryClient.invalidateQueries({ queryKey: RULES_QUERY_KEY });
    }),
  });
}

export function useCreateTemplate(): UseMutationResult<TemplateRowView, Error, TemplateFormValues> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<TemplateRowView, Error, TemplateFormValues>({
    mutationFn: async (body) => parseResponse(templateRowSchema, await api.post<unknown>("/notification-templates", { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: TEMPLATES_QUERY_KEY });
    },
  });
}

export function useUpdateTemplate(id: string): UseMutationResult<TemplateRowView, Error, TemplatePatchBody> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<TemplateRowView, Error, TemplatePatchBody>({
    mutationFn: async (body) => parseResponse(templateRowSchema, await api.patch<unknown>(templatePath(id), { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: TEMPLATES_QUERY_KEY });
    },
    onError: refreshIfStale(() => {
      void queryClient.invalidateQueries({ queryKey: TEMPLATES_QUERY_KEY });
    }),
  });
}

export interface PreviewBody {
  subject: string;
  body: string;
}

export function usePreviewTemplate(): UseMutationResult<PreviewView, Error, PreviewBody> {
  return useSensitiveMutation<PreviewView, Error, PreviewBody>({
    mutationFn: async (body) => parseResponse(previewSchema, await api.post<unknown>("/notification-templates/preview", { body })),
  });
}
