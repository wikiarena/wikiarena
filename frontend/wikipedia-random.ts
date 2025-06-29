interface RandomPageCache {
    pages: string[];
    timestamp: number;
}

class WikipediaRandomService {
    private cache: RandomPageCache | null = null;
    private readonly CACHE_DURATION = 10 * 60 * 1000; // 10 minutes
    private readonly RANDOM_PAGES_COUNT = 100;
    
    private cycleInterval: NodeJS.Timeout | null = null;
    private currentIndex = 0;
    private callbacks: Array<(title: string) => void> = [];

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
                `https://en.wikipedia.org/w/api.php?action=query&list=random&rnnamespace=0&rnlimit=${this.RANDOM_PAGES_COUNT}&format=json&origin=*`,
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
    }
}

export { WikipediaRandomService }; 