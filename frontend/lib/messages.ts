/**
 * 站内消息与通知 API 封装
 *
 * 对应接口文档：docs/MESSAGE_NOTIFICATION_FRONTEND_INTEGRATION.md
 * - 消息（message）：站内消息列表（带类型、定向、定时、已读）
 * - 通知（notification）：进入网站时的弹窗提示，全局同一时刻仅一条生效，
 *   用户关闭（dismiss）后不再弹出，可在「历史通知」回看
 * - 管理端：消息与通知各自的 CRUD、上下架、定向目标维护
 */

import { get, post } from "@/lib/request";

/** 消息类型枚举 */
export type MessageType = "notice" | "maintenance" | "update" | "activity";

export const MESSAGE_TYPES: MessageType[] = [
  "notice",
  "maintenance",
  "update",
  "activity",
];

/** 收件箱类别 */
export type InboxCategory = "message" | "notification";

/** 定向目标 */
export type MessageTargets = {
  user_ids: string[];
  token_group_ids: number[];
};

/** 用户端消息对象 */
export type InboxMessage = {
  id: string;
  title: string;
  /** markdown 原文 */
  content: string;
  type: MessageType;
  start_at: string;
  expires_at: string | null;
  created_at: string | null;
  is_read: boolean;
};

/** 用户端历史通知对象 */
export type InboxNotification = {
  id: string;
  title: string;
  content: string;
  start_at: string;
  expires_at: string | null;
  created_at: string | null;
  is_dismissed: boolean;
};

/** 管理端消息对象 */
export type AdminMessage = {
  id: string;
  title: string;
  content: string;
  type: MessageType;
  is_public: boolean;
  is_active: boolean;
  start_at: string;
  expires_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  targets: MessageTargets;
};

/** 管理端通知对象（无 type 字段） */
export type AdminNotification = Omit<AdminMessage, "type">;

export type Paged<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type UnreadCount = {
  message_unread_count: number;
  /** 未关闭的生效中通知数量（0 或 1） */
  notification_pending_count: number;
};

/* ---------------- 用户端：统一收件箱 ---------------- */

/** 查询收件箱列表（category=message 返回消息，category=notification 返回历史通知） */
export const listInboxMessages = (params?: {
  type?: MessageType;
  unread_only?: boolean;
  page?: number;
  page_size?: number;
}) =>
  get<Paged<InboxMessage> & { category: InboxCategory }>("/messages/list", {
    params: { ...params, category: "message" },
  });

export const listInboxNotifications = (params?: {
  page?: number;
  page_size?: number;
}) =>
  get<Paged<InboxNotification> & { category: InboxCategory }>(
    "/messages/list",
    { params: { ...params, category: "notification" } },
  );

/** 查询收件箱详情 */
export const getInboxMessageDetail = (messageId: string) =>
  get<InboxMessage & { category: InboxCategory }>("/messages/detail", {
    params: { category: "message", id: messageId },
  });

export const getInboxNotificationDetail = (notificationId: string) =>
  get<InboxNotification & { category: InboxCategory }>("/messages/detail", {
    params: { category: "notification", id: notificationId },
  });

/** 查询未读数与通知待处理数 */
export const getMessageUnreadCount = () =>
  get<UnreadCount>("/messages/unread-count");

/** 标记单条消息已读（幂等） */
export const markMessageRead = (messageId: string) =>
  post<{ success: boolean }>("/messages/mark-read", {
    message_id: messageId,
  });

/** 消息全部标记已读 */
export const markAllMessagesRead = () =>
  post<{ marked_count: number }>("/messages/mark-all-read");

/* ---------------- 用户端：弹窗通知 ---------------- */

/** 查询当前弹窗通知（无生效中通知或已关闭时为 null） */
export const getCurrentNotification = () =>
  get<{ notification: InboxNotification | null }>("/notifications/current");

/** 关闭通知（关闭后不再弹出，可在历史通知回看） */
export const dismissNotification = (notificationId: string) =>
  post<{ success: boolean }>("/notifications/dismiss", {
    notification_id: notificationId,
  });

/* ---------------- 管理端：消息 ---------------- */

/** 查询消息列表 */
export const listAdminMessages = (params?: {
  keyword?: string;
  type?: MessageType;
  is_active?: boolean;
  page?: number;
  page_size?: number;
}) => get<Paged<AdminMessage>>("/admin/messages/list", { params });

/** 查询消息详情 */
export const getAdminMessage = (messageId: string) =>
  get<AdminMessage>("/admin/messages/detail", {
    params: { message_id: messageId },
  });

/** 创建消息 */
export const createMessage = (body: {
  title: string;
  content: string;
  type: MessageType;
  is_public?: boolean;
  is_active?: boolean;
  start_at: string;
  expires_at?: string | null;
  targets?: MessageTargets;
}) => post<AdminMessage>("/admin/messages/create", body);

/** 更新消息（targets 提交即整体替换） */
export const updateMessage = (body: {
  message_id: string;
  title?: string;
  content?: string;
  type?: MessageType;
  is_public?: boolean;
  is_active?: boolean;
  start_at?: string;
  expires_at?: string | null;
  targets?: MessageTargets;
}) => post<AdminMessage>("/admin/messages/update", body);

/** 启用/下架消息 */
export const updateMessageStatus = (body: {
  message_id: string;
  is_active: boolean;
}) => post<AdminMessage>("/admin/messages/update-status", body);

/** 删除消息（逻辑删除） */
export const deleteMessage = (messageId: string) =>
  post<{ success: boolean }>("/admin/messages/delete", {
    message_id: messageId,
  });

/* ---------------- 管理端：通知 ---------------- */

/** 查询通知列表 */
export const listAdminNotifications = (params?: {
  keyword?: string;
  is_active?: boolean;
  page?: number;
  page_size?: number;
}) => get<Paged<AdminNotification>>("/admin/notifications/list", { params });

/** 查询通知详情 */
export const getAdminNotification = (notificationId: string) =>
  get<AdminNotification>("/admin/notifications/detail", {
    params: { notification_id: notificationId },
  });

/**
 * 创建通知（无 type 字段）
 * 注意：创建/更新/启用时会自动下架其它通知，保证全局仅一条生效中
 */
export const createNotification = (body: {
  title: string;
  content: string;
  is_public?: boolean;
  is_active?: boolean;
  start_at: string;
  expires_at?: string | null;
  targets?: MessageTargets;
}) => post<AdminNotification>("/admin/notifications/create", body);

/** 更新通知（targets 提交即整体替换） */
export const updateNotification = (body: {
  notification_id: string;
  title?: string;
  content?: string;
  is_public?: boolean;
  is_active?: boolean;
  start_at?: string;
  expires_at?: string | null;
  targets?: MessageTargets;
}) => post<AdminNotification>("/admin/notifications/update", body);

/** 启用/下架通知（启用时会自动下架其它通知） */
export const updateNotificationStatus = (body: {
  notification_id: string;
  is_active: boolean;
}) => post<AdminNotification>("/admin/notifications/update-status", body);

/** 删除通知（逻辑删除） */
export const deleteNotification = (notificationId: string) =>
  post<{ success: boolean }>("/admin/notifications/delete", {
    notification_id: notificationId,
  });
