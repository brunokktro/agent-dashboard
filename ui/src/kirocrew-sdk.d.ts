// @kirocrew/app-sdk is injected at runtime by the KiroCrew shell
// (window.__kirocrew_modules) and marked external in vite.config.ts -
// it has no npm package. Minimal typings for what this wrapper uses.
declare module '@kirocrew/app-sdk' {
  export interface AppApi {
    get<T = unknown>(path: string, init?: RequestInit): Promise<T>
    post<T = unknown>(path: string, body?: unknown): Promise<T>
    put<T = unknown>(path: string, body?: unknown): Promise<T>
    patch<T = unknown>(path: string, body?: unknown): Promise<T>
    del<T = unknown>(path: string): Promise<T>
  }
  export function useAppApi(): AppApi
}

declare module '@kirocrew/app-sdk/ui' {
  import type { FC, PropsWithChildren } from 'react'
  export const Card: FC<PropsWithChildren>
  export const CardTitle: FC<PropsWithChildren>
  export const PageHeader: FC<{ title: string; subtitle?: string }>
  export const StatCard: FC<{ label: string; value: string; accent?: boolean }>
}
