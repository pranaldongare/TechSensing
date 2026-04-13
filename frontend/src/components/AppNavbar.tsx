import React from 'react';
import { Moon, Sun } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTheme } from '@/lib/theme-context';
import { PROJECT_NAME } from '../../config';

const AppNavbar: React.FC = () => {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="border-b bg-background sticky top-0 z-10">
      <div className="px-4 py-3 flex justify-between items-center">
        <div className="flex items-center gap-2">
          <img
            src="/tile-intelligent-augmenter.svg"
            alt="Tech Sensing"
            className="w-6 h-6 object-contain"
            draggable={false}
          />
          <h1 className="text-lg font-semibold">{PROJECT_NAME}</h1>
        </div>
        <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
          {theme === 'light' ? <Moon className="w-5 h-5" /> : <Sun className="w-5 h-5" />}
        </Button>
      </div>
    </header>
  );
};

export default AppNavbar;
