import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import UpsetSection from '../UpsetSection';
import { Upset } from '../../../types/prediction';

const upsetWithPaths: Upset = {
  upset_index: 0.54,
  deterministic_component: 0.6,
  agent_component: 0.08,
  bounded_agent: 0.45,
  upset_signals: [],
  upset_paths: [
    'Path one: Germany come out flat and Curaçao sneak a set-piece goal.',
    'Path two: Curaçao park a deep block and frustrate Germany.',
    'Path three: Limited data means anything could happen.',
  ],
};

const upsetEmptyPaths: Upset = {
  upset_index: 0.277,
  deterministic_component: 0.217,
  agent_component: 0.45,
  bounded_agent: 0.367,
  upset_signals: [],
  upset_paths: [],
};

describe('UpsetSection', () => {
  test('renders nothing when favouriteProbability <= 0.65', () => {
    const { container } = render(
      <UpsetSection
        upset={upsetWithPaths}
        favouriteProbability={0.60}
        favouriteTeam="Germany"
        underdogName="Curaçao"
      />,
    );

    expect(container.firstChild).toBeNull();
  });

  test('renders nothing when upset_paths is empty even if favouriteProbability > 0.65', () => {
    const { container } = render(
      <UpsetSection
        upset={upsetEmptyPaths}
        favouriteProbability={0.80}
        favouriteTeam="Germany"
        underdogName="Curaçao"
      />,
    );

    expect(container.firstChild).toBeNull();
  });

  test('renders three numbered cards when both gates pass', () => {
    render(
      <UpsetSection
        upset={upsetWithPaths}
        favouriteProbability={0.865}
        favouriteTeam="Germany"
        underdogName="Curaçao"
      />,
    );

    expect(screen.getByTestId('upset-path-0')).toBeInTheDocument();
    expect(screen.getByTestId('upset-path-1')).toBeInTheDocument();
    expect(screen.getByTestId('upset-path-2')).toBeInTheDocument();
  });

  test('renders the agent upset_paths text verbatim in the cards', () => {
    render(
      <UpsetSection
        upset={upsetWithPaths}
        favouriteProbability={0.865}
        favouriteTeam="Germany"
        underdogName="Curaçao"
      />,
    );

    expect(screen.getByTestId('upset-path-0')).toHaveTextContent(
      'Path one: Germany come out flat and Curaçao sneak a set-piece goal.',
    );
    expect(screen.getByTestId('upset-path-1')).toHaveTextContent(
      'Path two: Curaçao park a deep block and frustrate Germany.',
    );
    expect(screen.getByTestId('upset-path-2')).toHaveTextContent(
      'Path three: Limited data means anything could happen.',
    );
  });

  test('section heading uses favouriteTeam name', () => {
    render(
      <UpsetSection
        upset={upsetWithPaths}
        favouriteProbability={0.865}
        favouriteTeam="Germany"
        underdogName="Curaçao"
      />,
    );

    expect(screen.getByTestId('upset-heading')).toHaveTextContent(
      'Three paths to Germany losing this.',
    );
  });

  test('upset risk meter shows formatPercent(upset_index, 1)', () => {
    render(
      <UpsetSection
        upset={upsetWithPaths}
        favouriteProbability={0.865}
        favouriteTeam="Germany"
        underdogName="Curaçao"
      />,
    );

    // upset_index = 0.54 → "54.0%"
    expect(screen.getByTestId('upset-meter')).toHaveTextContent('Upset risk: 54.0%');
  });

  test('share button renders', () => {
    render(
      <UpsetSection
        upset={upsetWithPaths}
        favouriteProbability={0.865}
        favouriteTeam="Germany"
        underdogName="Curaçao"
      />,
    );

    expect(screen.getByTestId('share-button')).toBeInTheDocument();
    expect(screen.getByTestId('share-button')).toHaveTextContent('Share');
  });

  test('share button copies URL to clipboard on desktop', async () => {
    // Mock clipboard API
    const writeText = jest.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: { writeText },
      share: undefined,
    });

    render(
      <UpsetSection
        upset={upsetWithPaths}
        favouriteProbability={0.865}
        favouriteTeam="Germany"
        underdogName="Curaçao"
      />,
    );

    await userEvent.click(screen.getByTestId('share-button'));

    expect(writeText).toHaveBeenCalledWith(window.location.href);
  });

  test('upset meter uses amber color when upset_index >= 0.4', () => {
    render(
      <UpsetSection
        upset={upsetWithPaths}
        favouriteProbability={0.865}
        favouriteTeam="Germany"
        underdogName="Curaçao"
      />,
    );

    // upset_index = 0.54 >= 0.4 → pink (#ec407a)
    const meter = screen.getByTestId('upset-meter');
    expect(meter).toBeInTheDocument();
  });

  test('upset meter uses grey color when upset_index < 0.4', () => {
    const lowUpset: Upset = {
      ...upsetWithPaths,
      upset_index: 0.25,
    };

    render(
      <UpsetSection
        upset={lowUpset}
        favouriteProbability={0.865}
        favouriteTeam="Germany"
        underdogName="Curaçao"
      />,
    );

    expect(screen.getByTestId('upset-meter')).toHaveTextContent('Upset risk: 25.0%');
  });

  // ── AbortError handling tests ─────────────────────────────────────

  test('share button silently ignores AbortError from navigator.share', async () => {
    const abortError = new DOMException('Share canceled', 'AbortError');
    const shareMock = jest.fn().mockRejectedValue(abortError);
    const writeText = jest.fn();
    Object.assign(navigator, {
      share: shareMock,
      clipboard: { writeText },
    });

    render(
      <UpsetSection
        upset={upsetWithPaths}
        favouriteProbability={0.865}
        favouriteTeam="Germany"
        underdogName="Curaçao"
      />,
    );

    await userEvent.click(screen.getByTestId('share-button'));

    expect(shareMock).toHaveBeenCalled();
    expect(writeText).not.toHaveBeenCalled();
  });

  test('share button falls through to clipboard on non-AbortError from navigator.share', async () => {
    const otherError = new Error('Something went wrong');
    const shareMock = jest.fn().mockRejectedValue(otherError);
    const writeText = jest.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      share: shareMock,
      clipboard: { writeText },
    });

    render(
      <UpsetSection
        upset={upsetWithPaths}
        favouriteProbability={0.865}
        favouriteTeam="Germany"
        underdogName="Curaçao"
      />,
    );

    await userEvent.click(screen.getByTestId('share-button'));

    expect(shareMock).toHaveBeenCalled();
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith(window.location.href);
    });
  });

  test('share button does not copy to clipboard when navigator.share succeeds', async () => {
    const shareMock = jest.fn().mockResolvedValue(undefined);
    const writeText = jest.fn();
    Object.assign(navigator, {
      share: shareMock,
      clipboard: { writeText },
    });

    render(
      <UpsetSection
        upset={upsetWithPaths}
        favouriteProbability={0.865}
        favouriteTeam="Germany"
        underdogName="Curaçao"
      />,
    );

    await userEvent.click(screen.getByTestId('share-button'));

    expect(shareMock).toHaveBeenCalledWith({
      title: 'Three paths to a Germany upset — FantasyFuel',
      url: window.location.href,
      text: 'Can Curaçao pull off the upset? See three ways Germany could lose.',
    });
    expect(writeText).not.toHaveBeenCalled();
  });
});
