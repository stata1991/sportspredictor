import { renderHook, waitFor, act } from '@testing-library/react';
import { useMatchPrediction } from './useMatchPrediction';
import api from '../../api';
import { PreMatchPredictionResponse } from '../types/prediction';
import { FULL_PREDICTIONS, FULL_REASONING, FULL_UPSET, FULL_RESPONSE } from '../__fixtures__/sampleResponse';

jest.mock('../../api');
const mockedApi = api as jest.Mocked<typeof api>;

describe('useMatchPrediction', () => {
  afterEach(() => {
    jest.resetAllMocks();
  });

  test('starts in loading state with all data fields null', () => {
    mockedApi.get.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useMatchPrediction('1489369'));

    expect(result.current.loading).toBe(true);
    expect(result.current.prediction).toBeNull();
    expect(result.current.reasoning).toBeNull();
    expect(result.current.upset).toBeNull();
    expect(result.current.stage).toBeNull();
    expect(result.current.partialAgent).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.errorKind).toBeNull();
  });

  test('undefined fixtureId returns idle state, no fetch', () => {
    const { result } = renderHook(() => useMatchPrediction(undefined));

    expect(result.current.loading).toBe(false);
    expect(result.current.prediction).toBeNull();
    expect(result.current.stage).toBeNull();
    expect(result.current.error).toBeNull();
    expect(mockedApi.get).not.toHaveBeenCalled();
  });

  test('empty string fixtureId returns idle state, no fetch', () => {
    const { result } = renderHook(() => useMatchPrediction(''));

    expect(result.current.loading).toBe(false);
    expect(result.current.prediction).toBeNull();
    expect(result.current.stage).toBeNull();
    expect(result.current.error).toBeNull();
    expect(mockedApi.get).not.toHaveBeenCalled();
  });

  test('successful full bundle populates all blocks', async () => {
    mockedApi.get.mockResolvedValueOnce({ data: FULL_RESPONSE });

    const { result } = renderHook(() => useMatchPrediction('1489369'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.prediction).toEqual(FULL_PREDICTIONS);
    expect(result.current.reasoning).toEqual(FULL_REASONING);
    expect(result.current.upset).toEqual(FULL_UPSET);
    expect(result.current.stage).toBe('pre_lineup');
    expect(result.current.homeTeam).toBe('Mexico');
    expect(result.current.awayTeam).toBe('South Africa');
    expect(result.current.partialAgent).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.errorKind).toBeNull();
  });

  test('partial bundle without reasoning sets partialAgent=true', async () => {
    const partial: PreMatchPredictionResponse = {
      ...FULL_RESPONSE,
      reasoning: null,
      upset: null,
    };
    mockedApi.get.mockResolvedValueOnce({ data: partial });

    const { result } = renderHook(() => useMatchPrediction('1489369'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.prediction).toEqual(FULL_PREDICTIONS);
    expect(result.current.reasoning).toBeNull();
    expect(result.current.upset).toBeNull();
    expect(result.current.stage).toBe('pre_lineup');
    expect(result.current.partialAgent).toBe(true);
    expect(result.current.error).toBeNull();
    expect(result.current.errorKind).toBeNull();
  });

  test('completed fixture populates prediction with stage=completed', async () => {
    const completed: PreMatchPredictionResponse = {
      fixture_id: 1489369,
      home_team: 'Mexico',
      away_team: 'South Africa',
      home_team_id: 16,
      away_team_id: 1531,
      status: 'FT',
      stage: 'completed',
      cached: true,
      message: 'Fixture already completed. Returning most recent pre-match predictions.',
      predictions: FULL_PREDICTIONS,
      reasoning: null,
      upset: null,
    };
    mockedApi.get.mockResolvedValueOnce({ data: completed });

    const { result } = renderHook(() => useMatchPrediction('1489369'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.prediction).toEqual(FULL_PREDICTIONS);
    expect(result.current.stage).toBe('completed');
    expect(result.current.partialAgent).toBe(true);
    expect(result.current.error).toBeNull();
    expect(result.current.errorKind).toBeNull();
  });

  test('422 not-predictable sets errorKind=not_predictable', async () => {
    const axiosError = Object.assign(new Error('Request failed with status code 422'), {
      isAxiosError: true,
      response: {
        status: 422,
        data: { detail: "Fixture status 'PST' is not predictable" },
      },
    });
    mockedApi.get.mockRejectedValueOnce(axiosError);

    const { result } = renderHook(() => useMatchPrediction('1489369'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).not.toBeNull();
    expect(result.current.errorKind).toBe('not_predictable');
    expect(result.current.prediction).toBeNull();
    expect(result.current.stage).toBeNull();
  });

  test('network failure with no response sets errorKind=network', async () => {
    const networkError = Object.assign(new Error('Network Error'), {
      isAxiosError: true,
      response: undefined,
    });
    mockedApi.get.mockRejectedValueOnce(networkError);

    const { result } = renderHook(() => useMatchPrediction('1489369'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).not.toBeNull();
    expect(result.current.error?.message).toBe('Network Error');
    expect(result.current.errorKind).toBe('network');
    expect(result.current.prediction).toBeNull();
  });

  test('500 server error sets errorKind=network', async () => {
    const serverError = Object.assign(new Error('Request failed with status code 500'), {
      isAxiosError: true,
      response: {
        status: 500,
        data: 'Internal Server Error',
      },
    });
    mockedApi.get.mockRejectedValueOnce(serverError);

    const { result } = renderHook(() => useMatchPrediction('1489369'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).not.toBeNull();
    expect(result.current.errorKind).toBe('network');
  });

  test('does not warn when unmounted before fetch resolves', async () => {
    const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});

    mockedApi.get.mockReturnValue(new Promise(() => {}));

    const { unmount } = renderHook(() => useMatchPrediction('1489369'));

    const signal = mockedApi.get.mock.calls[0][1]?.signal as AbortSignal;
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(signal.aborted).toBe(false);

    unmount();

    expect(signal.aborted).toBe(true);

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    expect(errorSpy).not.toHaveBeenCalled();
    expect(warnSpy).not.toHaveBeenCalled();

    errorSpy.mockRestore();
    warnSpy.mockRestore();
  });

  test('404 fixture not found sets errorKind=not_found', async () => {
    const notFoundError = Object.assign(new Error('Request failed with status code 404'), {
      isAxiosError: true,
      response: {
        status: 404,
        data: { detail: 'Fixture 999999999 not found' },
      },
    });
    mockedApi.get.mockRejectedValueOnce(notFoundError);

    const { result } = renderHook(() => useMatchPrediction('999999999'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).not.toBeNull();
    expect(result.current.error?.message).toBe('Request failed with status code 404');
    expect(result.current.errorKind).toBe('not_found');
    expect(result.current.prediction).toBeNull();
    expect(result.current.stage).toBeNull();
  });
});
