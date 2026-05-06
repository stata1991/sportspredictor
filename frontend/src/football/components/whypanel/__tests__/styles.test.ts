import { formatSource, sectionLabelSx } from '../styles';

describe('formatSource', () => {
  test('maps get_team_form to "Recent form"', () => {
    expect(formatSource('get_team_form')).toBe('Recent form');
  });

  test('maps get_head_to_head to "Head-to-head"', () => {
    expect(formatSource('get_head_to_head')).toBe('Head-to-head');
  });

  test('maps get_injuries to "Injuries"', () => {
    expect(formatSource('get_injuries')).toBe('Injuries');
  });

  test('maps get_market_consensus to "Market odds"', () => {
    expect(formatSource('get_market_consensus')).toBe('Market odds');
  });

  test('maps prediction_context to "Model state"', () => {
    expect(formatSource('prediction_context')).toBe('Model state');
  });

  test('returns raw string for unknown source', () => {
    expect(formatSource('some_unknown_tool')).toBe('some_unknown_tool');
  });
});

describe('sectionLabelSx', () => {
  test('has expected properties', () => {
    expect(sectionLabelSx.color).toBe('#b0bec5');
    expect(sectionLabelSx.textTransform).toBe('uppercase');
  });
});
