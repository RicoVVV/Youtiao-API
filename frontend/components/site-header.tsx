import { LocaleLink } from "./locale-link";
import { HeaderAuth } from "./header-auth";
import { MainNav } from "./main-nav";
import { LocaleSwitcher } from "./locale-switcher";
import { ThemeSwitcher } from "./theme-switcher";
import { SiteLogo } from "./site-logo";
import { SiteName } from "./site-name";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-50 h-14 w-full border-b bg-background/80 backdrop-blur-sm">
      <div className="relative mx-auto flex h-full max-w-6xl items-center px-4 sm:px-6">
        <LocaleLink href="/" className="flex items-center gap-2 font-semibold">
          <SiteLogo />
          <SiteName />
        </LocaleLink>

        {/* 导航在内容区水平居中 */}
        <div className="absolute left-1/2 -translate-x-1/2">
          <MainNav />
        </div>
      </div>

      {/* 固定在视口右上角：主题切换 + 语言切换 + 账户头像，垂直与 h-14 头部对齐 */}
      <div className="fixed right-4 top-0 z-[60] flex h-14 items-center gap-3">
        <ThemeSwitcher />
        <LocaleSwitcher />
        <HeaderAuth />
      </div>
    </header>
  );
}
