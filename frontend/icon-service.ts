interface IconURLs {
    primary: string;
    fallback: string;
}

// Centralized logic for determining icon URLs.
export function getIconUrls(model: { provider: string, icon_slug: string }): IconURLs {
    // Special handling for local/custom icons.
    if (model.provider === 'wikiarena') {
        // SIMPLIFICATION: Defaulting to dark version for the dark UI.
        const url = `/assets/icons/dice-dark.svg`;
        return {
            primary: url,
            fallback: url, // No specific fallback for the SVG, it should just load.
        };
    }

    // Default to LobeHub CDN for all other providers.
    return {
        primary: `https://unpkg.com/@lobehub/icons-static-png@latest/dark/${model.icon_slug}-color.png`,
        fallback: `https://unpkg.com/@lobehub/icons-static-png@latest/dark/${model.icon_slug}.png`,
    };
}

// Helper to apply URLs and fallbacks to a standard <img> element.
export function setIcon(imgElement: HTMLImageElement, model: { provider: string, icon_slug: string }) {
    const urls = getIconUrls(model);

    imgElement.src = urls.primary;
    imgElement.alt = `${model.provider} icon`;

    // Set up a multi-stage fallback system.
    imgElement.onerror = () => {
        // If primary fails, try the fallback (e.g., mono version for LobeHub).
        imgElement.src = urls.fallback;
        // If the fallback ALSO fails, use the universal, local question mark icon.
        imgElement.onerror = () => {
            imgElement.src = '/assets/icons/question-mark.svg';
            imgElement.onerror = null; // Final fallback, prevent infinite loops.
        };
    };
} 