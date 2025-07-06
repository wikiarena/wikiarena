interface RandomPageCache {
    pages: string[];
    timestamp: number;
}

class WikipediaRandomService {
    private cache: RandomPageCache | null = null;
    private readonly CACHE_DURATION = 10 * 60 * 1000; // 10 minutes
    private readonly RANDOM_PAGES_COUNT = 200; // bulk checking limit
    
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
            const titles = pages.map((page: any) => page.title);

            // Cache the results
            this.cache = {
                pages: titles,
                timestamp: Date.now()
            };

            return titles;
        } catch (error) {
            console.error('Failed to fetch random Wikipedia pages:', error);
            return [];
        }
    }

    /**
     * Get a random page title
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