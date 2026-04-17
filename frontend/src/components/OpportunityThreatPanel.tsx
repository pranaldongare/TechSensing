import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Target, ShieldAlert, Lightbulb } from 'lucide-react';

interface OpportunityThreat {
  org_context_used: string;
  opportunities: string[];
  threats: string[];
  recommended_actions: string[];
}

interface Props {
  data?: OpportunityThreat | null;
}

/** Two-column opportunities vs threats card (#33). */
const OpportunityThreatPanel: React.FC<Props> = ({ data }) => {
  if (!data) return null;

  const hasContent =
    (data.opportunities?.length ?? 0) > 0 ||
    (data.threats?.length ?? 0) > 0 ||
    (data.recommended_actions?.length ?? 0) > 0;

  if (!hasContent) return null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Target className="w-4 h-4 text-primary" />
          Opportunity / Threat Framing
          {data.org_context_used && (
            <Badge variant="outline" className="text-[10px] font-normal ml-2">
              for {data.org_context_used}
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Opportunities */}
          {data.opportunities?.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-xs font-medium text-green-700 dark:text-green-400">
                <Target className="w-3 h-3" />
                Opportunities
              </div>
              <ul className="space-y-1.5">
                {data.opportunities.map((o, i) => (
                  <li
                    key={i}
                    className="text-xs text-muted-foreground leading-relaxed pl-3 border-l-2 border-green-300 dark:border-green-700"
                  >
                    {o}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Threats */}
          {data.threats?.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-xs font-medium text-red-700 dark:text-red-400">
                <ShieldAlert className="w-3 h-3" />
                Threats
              </div>
              <ul className="space-y-1.5">
                {data.threats.map((t, i) => (
                  <li
                    key={i}
                    className="text-xs text-muted-foreground leading-relaxed pl-3 border-l-2 border-red-300 dark:border-red-700"
                  >
                    {t}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Recommended actions */}
        {data.recommended_actions?.length > 0 && (
          <div className="mt-4 space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-medium">
              <Lightbulb className="w-3 h-3 text-amber-500" />
              Recommended actions
            </div>
            <ol className="space-y-1 list-decimal list-inside">
              {data.recommended_actions.map((a, i) => (
                <li
                  key={i}
                  className="text-xs text-muted-foreground leading-relaxed"
                >
                  {a}
                </li>
              ))}
            </ol>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default OpportunityThreatPanel;
