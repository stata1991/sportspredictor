import { AFFixture } from './fixture';

export interface WorldCupOutletContext {
  fixtures: AFFixture[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onFixtureClick: (fixtureId: number) => void;
}
