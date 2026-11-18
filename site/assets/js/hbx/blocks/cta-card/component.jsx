/**
 * CTA Card Block Component
 * A centered card with title, text, and primary action button.
 * Supports glassmorphism, custom backgrounds, and automatic text color adjustment.
 */

import {Icon} from "../../shared/components/Icon.jsx";

// Simple markdown renderer
function renderText(text) {
  if (!text) return "";
  return String(text)
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/`(.*?)`/g, "<code>$1</code>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
}

export const CtaCardBlock = ({content, design, _id, button_icon_svg}) => {
  const card = design?.card || {};
  const cardClass = card.css_class || "";
  const cardStyle = card.css_style || "";

  // Overlay Opacity Logic
  let overlayOpacity = 0.15;
  if (card.overlay_opacity !== undefined) {
    const val = parseFloat(card.overlay_opacity);
    if (!Number.isNaN(val)) overlayOpacity = Math.max(0, Math.min(1, val));
  }

  // Text Color Logic — three modes:
  // - "light": white title + white/80 body, white pill button (use on coloured/dark cards)
  // - "dark":  dark title + dark body, dark pill button (use on white/light cards)
  // - "auto":  detect from card classes — colored gradient or saturated bg → light, else fall back
  //
  // All output classes must be FULL LITERAL STRINGS so Tailwind's source scanner picks them up.
  let textColorMode = "auto";
  if (["light", "dark", "auto"].includes(card.text_color?.toLowerCase())) {
    textColorMode = card.text_color.toLowerCase();
  }

  if (textColorMode === "auto") {
    const looksColored =
      cardClass.includes("bg-gradient") ||
      /\bbg-(primary|secondary|violet|indigo|blue|purple|pink|fuchsia|rose|red|orange|amber|emerald|teal|cyan|sky)-[4-9]\d{0,2}\b/.test(cardClass) ||
      /\bfrom-(primary|secondary|violet|indigo|blue|purple|pink|fuchsia|rose|red|orange|amber|emerald|teal|cyan|sky)-[4-9]/.test(cardClass);
    // Legacy detection: design.background.gradient.start using saturated Tailwind tokens
    const bg = design?.background || {};
    const gradientStart = bg.gradient?.start || "";
    const legacyDarkBg = ["primary-7", "primary-8", "primary-9", "secondary-7", "secondary-8", "secondary-9"].some((p) =>
      gradientStart.startsWith(p),
    );
    textColorMode = looksColored || legacyDarkBg ? "light" : "dark";
  }

  // Title, body, and button classes — full literals only
  const titleClasses = textColorMode === "light" ? "text-white" : "text-gray-900 dark:text-white";
  const bodyClasses = textColorMode === "light" ? "text-white/80" : "text-gray-700 dark:text-gray-300";
  // Button: in "light" mode (coloured card), a white control; in "dark" mode a dark one
  // (dark theme: off-white fill with dark text). Hairline ring, no glow shadow.
  const buttonBgClasses =
    textColorMode === "light"
      ? "bg-white ring-1 ring-black/10 hover:bg-gray-100"
      : "bg-gray-900 dark:bg-[#eef0f5] ring-1 ring-gray-900/10 dark:ring-white/10 hover:bg-gray-800 dark:hover:bg-white";
  const buttonTextClasses = textColorMode === "light" ? "text-gray-900" : "text-white dark:text-[#0b0d14]";

  // Button Logic
  const button = content?.button || {};
  const buttonText = button.text?.trim();
  const buttonUrl = button.url?.trim();
  const showButton = !!(buttonText && buttonUrl);

  let isExternal = false;
  let isNewTab = button.new_tab === true;
  if (buttonUrl) {
    try {
      const url = new URL(buttonUrl, window.location.origin);
      isExternal = url.origin !== window.location.origin;
    } catch {
      isExternal = /^https?:\/\//.test(buttonUrl);
    }
    if (buttonUrl.endsWith(".pdf")) isNewTab = true;
    if (isExternal) isNewTab = true;
  }

  const defaultBgClass = "bg-white dark:bg-white/[0.04] ring-1 ring-black/5 dark:ring-white/10";
  const finalCardClass = cardClass || defaultBgClass;

  const style = `--glassmorphism-opacity: ${overlayOpacity}; ${cardStyle}`;

  return (
    <div
      class={`relative overflow-hidden ${finalCardClass} p-8 sm:p-12 mx-auto max-w-6xl rounded-2xl flex flex-col items-center text-center`}
      style={style}
    >
      {/* Title */}
      {content.title && (
        <h2
          class={`${titleClasses} text-4xl sm:text-5xl lg:text-6xl font-medium leading-tight`}
          dangerouslySetInnerHTML={{__html: renderText(content.title)}}
        />
      )}

      {/* Text */}
      {content.text && (
        <div
          class={`${bodyClasses} mt-6 text-lg sm:text-xl max-w-3xl leading-relaxed`}
          dangerouslySetInnerHTML={{__html: renderText(content.text)}}
        />
      )}

      {/* Button */}
      {showButton && (
        <div class="flex mt-10">
          <a
            href={buttonUrl}
            target={isNewTab ? "_blank" : undefined}
            rel={isNewTab ? "noopener" : undefined}
            class={`group inline-flex items-center gap-3 rounded-lg px-5 py-2.5 text-lg font-medium ${buttonBgClasses} ${buttonTextClasses} transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50`}
          >
            <span>{buttonText}</span>
            {button_icon_svg && (
              <span>
                <Icon svg={button_icon_svg} attributes={{style: "height: 1.25em", class: "inline-block"}} />
              </span>
            )}
          </a>
        </div>
      )}
    </div>
  );
};
