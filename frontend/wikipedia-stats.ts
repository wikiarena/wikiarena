interface WikipediaStats {
    articles: number;
    pages: number;
    users: number;
    activeUsers: number;
    edits: number;
    images: number;
    timestamp: number;
}

interface StatsCache {
    stats: WikipediaStats;
    timestamp: number;
}

class WikipediaStatsService {
    private cache: StatsCache | null = null;
    private readonly CACHE_DURATION = 24 * 60 * 60 * 1000; // 24 hours
    
    /**
     * Fetch Wikipedia statistics from the API
     */
    async fetchStats(): Promise<WikipediaStats | null> {
        // Check cache first
        if (this.cache && Date.now() - this.cache.timestamp < this.CACHE_DURATION) {
            return this.cache.stats;
        }

        try {
            const response = await fetch(
                'https://en.wikipedia.org/w/api.php?action=query&meta=siteinfo&siprop=statistics&format=json&origin=*',
                {
                    headers: {
                        'Accept': 'application/json',
                    }
                }
            );

            if (!response.ok) {
                throw new Error(`Wikipedia Stats API error: ${response.status}`);
            }

            const data = await response.json();
            const statistics = data.query?.statistics;
            
            if (!statistics) {
                throw new Error('No statistics found in API response');
            }

            const stats: WikipediaStats = {
                articles: statistics.articles || 0,
                pages: statistics.pages || 0,
                users: statistics.users || 0,
                activeUsers: statistics.activeusers || 0,
                edits: statistics.edits || 0,
                images: statistics.images || 0,
                timestamp: Date.now()
            };

            // Cache the results
            this.cache = {
                stats,
                timestamp: Date.now()
            };

            return stats;
        } catch (error) {
            console.error('Failed to fetch Wikipedia statistics:', error);
            return null;
        }
    }

    /**
     * Get formatted article count with commas
     */
    async getArticleCount(): Promise<string> {
        const stats = await this.fetchStats();
        if (!stats) return '7,000,000'; // fallback
        
        return this.formatNumber(stats.articles);
    }

    /**
     * Get formatted task count (articles squared) with commas
     */
    async getTaskCount(): Promise<string> {
        const stats = await this.fetchStats();
        if (!stats) return '49,000,000,000,000'; // fallback
        
        const taskCount = Math.pow(stats.articles, 2);
        return this.formatNumber(taskCount);
    }

    /**
     * Get all formatted stats for display
     */
    async getFormattedStats(): Promise<{
        articles: string;
        tasks: string;
        articlesNumber: number;
        tasksNumber: number;
    }> {
        const stats = await this.fetchStats();
        
        if (!stats) {
            return {
                articles: '7,000,000',
                tasks: '49,000,000,000,000',
                articlesNumber: 7000000,
                tasksNumber: 49000000000000
            };
        }

        const tasksNumber = Math.pow(stats.articles, 2);
        
        return {
            articles: this.formatNumber(stats.articles),
            tasks: this.formatNumber(tasksNumber),
            articlesNumber: stats.articles,
            tasksNumber: tasksNumber
        };
    }

    /**
     * Format number with commas
     */
    private formatNumber(num: number): string {
        return num.toLocaleString('en-US');
    }

    /**
     * Clear the cache to force fresh data
     */
    clearCache(): void {
        this.cache = null;
    }

    /**
     * Check if cache is valid
     */
    isCacheValid(): boolean {
        return this.cache !== null && Date.now() - this.cache.timestamp < this.CACHE_DURATION;
    }
}

export { WikipediaStatsService, type WikipediaStats }; 