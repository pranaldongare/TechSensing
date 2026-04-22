import React from 'react';
import { NavLink } from 'react-router-dom';
import { Moon, Sun, Radar, Building2, Briefcase, Cpu, BarChart3, Settings } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTheme } from '@/lib/theme-context';
import { PROJECT_NAME } from '../../config';

const AppNavbar: React.FC = () => {
  const { theme, toggleTheme } = useTheme();

  const linkClass = ({ isActive }: { isActive: boolean }): string =>
    `inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
      isActive
        ? 'bg-primary/10 text-primary'
        : 'text-muted-foreground hover:text-foreground hover:bg-muted/60'
    }`;

  return (
    <header className="border-b bg-background sticky top-0 z-10">
      <div className="px-4 py-3 flex justify-between items-center gap-4">
        <div className="flex items-center gap-2 shrink-0">
          <img
            src="/tile-intelligent-augmenter.svg"
            alt="Tech Sensing"
            className="w-6 h-6 object-contain"
            draggable={false}
          />
          <h1 className="text-lg font-semibold">{PROJECT_NAME}</h1>
        </div>
        <nav className="flex items-center gap-1 flex-1 justify-center">
          <NavLink to="/" end className={linkClass}>
            <Radar className="w-4 h-4" />
            Tech Sensing
          </NavLink>
          <NavLink to="/company-analysis" className={linkClass}>
            <Building2 className="w-4 h-4" />
            Company Analysis
          </NavLink>
          <NavLink to="/key-companies" className={linkClass}>
            <Briefcase className="w-4 h-4" />
            Key Companies
          </NavLink>
          <NavLink to="/model-releases" className={linkClass}>
            <Cpu className="w-4 h-4" />
            Model Releases
          </NavLink>
          <NavLink to="/ai-leaderboard" className={linkClass}>
            <BarChart3 className="w-4 h-4" />
            AI Leaderboard
          </NavLink>
          <NavLink to="/settings" className={linkClass}>
            <Settings className="w-4 h-4" />
            Settings
          </NavLink>
        </nav>
        <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
          {theme === 'light' ? <Moon className="w-5 h-5" /> : <Sun className="w-5 h-5" />}
        </Button>
      </div>
    </header>
  );
};

export default AppNavbar;
