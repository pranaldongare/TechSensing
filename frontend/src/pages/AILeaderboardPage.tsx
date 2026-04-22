import React from 'react';
import { BarChart3 } from 'lucide-react';
import AppNavbar from '@/components/AppNavbar';
import AILeaderboardView from '@/components/AILeaderboardView';

const AILeaderboardPage: React.FC = () => {
  return (
    <div className="h-screen flex flex-col">
      <AppNavbar />
      <div className="flex-1 flex flex-col p-6 gap-4 overflow-hidden min-h-0">
        <div className="flex items-center gap-3 shrink-0">
          <BarChart3 className="w-6 h-6 text-primary" />
          <div>
            <h2 className="text-2xl font-bold leading-tight">AI Leaderboard</h2>
            <p className="text-xs text-muted-foreground">
              AI model rankings across quality, speed, price, and media categories from Artificial Analysis.
            </p>
          </div>
        </div>
        <div className="flex-1 overflow-auto min-h-0">
          <AILeaderboardView />
        </div>
      </div>
    </div>
  );
};

export default AILeaderboardPage;
