interface RandomPageCache {
    pages: string[];
    timestamp: number;
}

interface ValidatedPageCache {
    pages: string[];
    timestamp: number;
}

class WikipediaRandomService {
    private cache: RandomPageCache | null = null;
    private validatedStartPageCache: ValidatedPageCache | null = null;
    private validatedTargetPageCache: ValidatedPageCache | null = null;
    private readonly CACHE_DURATION = 10 * 60 * 1000; // 10 minutes
    private readonly RANDOM_PAGES_COUNT = 100;
    
    private cycleInterval: NodeJS.Timeout | null = null;
    private callbacks: Array<(title: string) => void> = [];

    /**
     * Check if a page has outgoing links (valid for start page)
     */
    async hasOutgoingLinks(pageTitle: string): Promise<boolean> {
        try {
            const response = await fetch(
                `https://en.wikipedia.org/w/api.php?action=query&titles=${encodeURIComponent(pageTitle)}&prop=links&pllimit=1&format=json&origin=*`
            );

            if (!response.ok) {
                return false;
            }

            const data = await response.json();
            const pages = data.query?.pages;
            
            if (!pages) {
                return false;
            }

            // Check if any page has links
            for (const page of Object.values(pages)) {
                if ((page as any).links && Array.isArray((page as any).links) && (page as any).links.length > 0) {
                    return true;
                }
            }
            
            return false;
        } catch (error) {
            console.error(`Error checking outgoing links for ${pageTitle}:`, error);
            return false;
        }
    }

    /**
     * Check if a page has incoming links (valid for target page)
     */
    async hasIncomingLinks(pageTitle: string): Promise<boolean> {
        try {
            const response = await fetch(
                `https://en.wikipedia.org/w/api.php?action=query&list=backlinks&bltitle=${encodeURIComponent(pageTitle)}&bllimit=1&format=json&origin=*`
            );

            if (!response.ok) {
                return false;
            }

            const data = await response.json();
            const backlinks = data.query?.backlinks;
            
            return Array.isArray(backlinks) && backlinks.length > 0;
        } catch (error) {
            console.error(`Error checking incoming links for ${pageTitle}:`, error);
            return false;
        }
    }

    /**
     * Fetch random Wikipedia page titles
     */
    async fetchRandomPages(): Promise<string[]> {
        // Check cache first
        if (this.cache && Date.now() - this.cache.timestamp < this.CACHE_DURATION) {
            return this.cache.pages;
        }

        try {
            const response = await fetch(
                `https://en.wikipedia.org/w/api.php?action=query&list=random&rnnamespace=0&rnfilterredir=nonredirects&rnlimit=${this.RANDOM_PAGES_COUNT}&format=json&origin=*`,
                {
                    headers: {
                        'Accept': 'application/json',
                    }
                }
            );

            if (!response.ok) {
                throw new Error(`Wikipedia Random API error: ${response.status}`);
            }

            const data = await response.json();
            const pages = data.query?.random || [];
            
            const titles = pages
                .map((page: any) => page.title)
                .filter((title: string) => {
                    // Filter out boring/technical pages
                    const lower = title.toLowerCase();
                    return !lower.includes('user:') && 
                           !lower.includes('talk:') &&
                           !lower.includes('category:') &&
                           !lower.includes('template:') &&
                           !lower.includes('wikipedia:') &&
                           !lower.includes('file:') &&
                           !lower.includes('help:') &&
                           !lower.includes('portal:') &&
                           !lower.includes('list of') &&
                           title.length > 2 && 
                           title.length < 50; // Keep interesting, readable titles
                });

            // Cache the results
            this.cache = {
                pages: titles,
                timestamp: Date.now()
            };

            return titles;
        } catch (error) {
            console.error('Failed to fetch random Wikipedia pages:', error);
            // Return fallback titles if API fails
            return [
                'Ancient Rome', 'Quantum Physics', 'Chocolate', 'Mount Everest', 'Jazz Music',
                'Ocean Currents', 'Renaissance Art', 'Space Exploration', 'Coffee Culture', 'Photography',
                'Marine Biology', 'Medieval History', 'Solar System', 'Classical Music', 'Architecture',
                'Geology', 'World Cuisine', 'Film History', 'Astronomy', 'Literature'
            ];
        }
    }

    /**
     * Fetch random pages that are valid for use as start pages (have outgoing links)
     */
    async fetchValidStartPages(): Promise<string[]> {
        // Check cache first
        if (this.validatedStartPageCache && Date.now() - this.validatedStartPageCache.timestamp < this.CACHE_DURATION) {
            return this.validatedStartPageCache.pages;
        }

        const allPages = await this.fetchRandomPages();
        const validStartPages: string[] = [];
        
        // Test pages in batches to avoid overwhelming the API
        const batchSize = 10;
        for (let i = 0; i < allPages.length && validStartPages.length < 20; i += batchSize) {
            const batch = allPages.slice(i, i + batchSize);
            const validationPromises = batch.map(async (page) => {
                try {
                    const hasLinks = await this.hasOutgoingLinks(page);
                    return hasLinks ? page : null;
                } catch {
                    return null;
                }
            });
            
            const batchResults = await Promise.all(validationPromises);
            const validInBatch = batchResults.filter((page): page is string => page !== null);
            validStartPages.push(...validInBatch);
        }

        // Cache the results
        this.validatedStartPageCache = {
            pages: validStartPages,
            timestamp: Date.now()
        };

        return validStartPages;
    }

    /**
     * Fetch random pages that are valid for use as target pages (have incoming links)
     */
    async fetchValidTargetPages(): Promise<string[]> {
        // Check cache first
        if (this.validatedTargetPageCache && Date.now() - this.validatedTargetPageCache.timestamp < this.CACHE_DURATION) {
            return this.validatedTargetPageCache.pages;
        }

        const allPages = await this.fetchRandomPages();
        const validTargetPages: string[] = [];
        
        // Test pages in batches to avoid overwhelming the API
        const batchSize = 10;
        for (let i = 0; i < allPages.length && validTargetPages.length < 20; i += batchSize) {
            const batch = allPages.slice(i, i + batchSize);
            const validationPromises = batch.map(async (page) => {
                try {
                    const hasLinks = await this.hasIncomingLinks(page);
                    return hasLinks ? page : null;
                } catch {
                    return null;
                }
            });
            
            const batchResults = await Promise.all(validationPromises);
            const validInBatch = batchResults.filter((page): page is string => page !== null);
            validTargetPages.push(...validInBatch);
        }

        // Cache the results
        this.validatedTargetPageCache = {
            pages: validTargetPages,
            timestamp: Date.now()
        };

        return validTargetPages;
    }

    /**
     * Get a random valid start page (has outgoing links)
     */
    async getRandomStartPage(): Promise<string> {
        const validPages = await this.fetchValidStartPages();
        if (validPages.length === 0) {
            // Fallback to any random page if validation fails
            const fallbackPages = await this.fetchRandomPages();
            return fallbackPages.length > 0 ? fallbackPages[Math.floor(Math.random() * fallbackPages.length)] : 'Ancient Rome';
        }
        
        return validPages[Math.floor(Math.random() * validPages.length)];
    }

    /**
     * Get a random valid target page (has incoming links)
     */
    async getRandomTargetPage(excludePage?: string): Promise<string> {
        const validPages = await this.fetchValidTargetPages();
        const availablePages = excludePage ? validPages.filter(page => page !== excludePage) : validPages;
        
        if (availablePages.length === 0) {
            // Fallback to any random page if validation fails
            const fallbackPages = await this.fetchRandomPages();
            const availableFallback = excludePage ? fallbackPages.filter(page => page !== excludePage) : fallbackPages;
            return availableFallback.length > 0 ? availableFallback[Math.floor(Math.random() * availableFallback.length)] : 'Quantum Physics';
        }
        
        return availablePages[Math.floor(Math.random() * availablePages.length)];
    }

    /**
     * Start cycling through random page titles
     */
    async startCycling(callback: (title: string) => void, intervalMs = 1500): Promise<void> {
        // Add callback to list
        this.callbacks.push(callback);

        // If already cycling, just add the callback
        if (this.cycleInterval) {
            return;
        }

        // Fetch random pages
        const pages = await this.fetchRandomPages();
        if (pages.length === 0) return;

        // Start cycling
        let currentIndex = 0;
        
        // Immediately show first title
        this.broadcastCurrentTitle(pages[currentIndex]);

        this.cycleInterval = setInterval(() => {
            currentIndex = (currentIndex + 1) % pages.length;
            this.broadcastCurrentTitle(pages[currentIndex]);
        }, intervalMs);
    }

    /**
     * Stop cycling and clear callbacks
     */
    stopCycling(): void {
        if (this.cycleInterval) {
            clearInterval(this.cycleInterval);
            this.cycleInterval = null;
        }
        this.callbacks = [];
    }

    /**
     * Remove a specific callback
     */
    removeCallback(callback: (title: string) => void): void {
        this.callbacks = this.callbacks.filter(cb => cb !== callback);
        
        // If no more callbacks, stop cycling
        if (this.callbacks.length === 0) {
            this.stopCycling();
        }
    }

    /**
     * Broadcast current title to all callbacks
     */
    private broadcastCurrentTitle(title: string): void {
        this.callbacks.forEach(callback => {
            try {
                callback(title);
            } catch (error) {
                console.error('Error in random title callback:', error);
            }
        });
    }

    /**
     * Get a random title immediately (without cycling)
     */
    async getRandomTitle(): Promise<string> {
        const pages = await this.fetchRandomPages();
        if (pages.length === 0) return 'Search Wikipedia...';
        
        return pages[Math.floor(Math.random() * pages.length)];
    }

    /**
     * Clear the cache to force fresh data
     */
    clearCache(): void {
        this.cache = null;
        this.validatedStartPageCache = null;
        this.validatedTargetPageCache = null;
    }

    /**
     * Slot machine effect: starts fast and slows down to a final selection
     */
    async startSlotMachine(callback: (title: string, isSpinning: boolean) => void): Promise<string> {
        const pages = await this.fetchRandomPages();
        if (pages.length === 0) return 'Search Wikipedia...';

        return new Promise((resolve) => {
            let currentIndex = 0;
            let spinCount = 0;
            const minSpins = 20; // Minimum number of spins
            const maxSpins = 30; // Maximum number of spins
            const totalSpins = minSpins + Math.floor(Math.random() * (maxSpins - minSpins));
            
            // Define spin intervals (in ms) for each phase
            const getIntervalForSpin = (spin: number, total: number): number => {
                const progress = spin / total;
                
                if (progress < 0.6) {
                    // Fast spinning phase (60% of spins)
                    return 50 + Math.random() * 30; // 50-80ms
                } else if (progress < 0.85) {
                    // Slow down phase (25% of spins)
                    return 80 + (progress - 0.6) * 400; // 80-180ms
                } else {
                    // Final slow phase (15% of spins)
                    return 180 + (progress - 0.85) * 800; // 180-300ms
                }
            };
            
            const performSpin = () => {
                currentIndex = (currentIndex + 1) % pages.length;
                spinCount++;
                
                // Update the display
                callback(pages[currentIndex], true);
                
                // Check if we should stop
                if (spinCount >= totalSpins) {
                    // Final callback with spinning = false
                    callback(pages[currentIndex], false);
                    resolve(pages[currentIndex]);
                    return;
                }
                
                // Schedule next spin with dynamic interval
                const nextInterval = getIntervalForSpin(spinCount, totalSpins);
                (this as any)._currentSlotTimer = setTimeout(performSpin, nextInterval);
            };
            
            // Start spinning immediately
            callback(pages[currentIndex], true);
            
            // Start the slot machine
            const firstInterval = getIntervalForSpin(0, totalSpins);
            (this as any)._currentSlotTimer = setTimeout(performSpin, firstInterval);
        });
    }

    /**
     * Stop any ongoing slot machine effect
     */
    stopSlotMachine(): void {
        if ((this as any)._currentSlotTimer) {
            clearTimeout((this as any)._currentSlotTimer);
            (this as any)._currentSlotTimer = null;
        }
    }
}

export { WikipediaRandomService }; 